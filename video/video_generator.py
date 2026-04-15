# video/video_generator.py
"""
AI動画生成クライアント

話題キーワードからアニメスタイルの短尺動画を生成し、
OBS Browser Sourceに配信する。

アーキテクチャ:
  topic_change → build_prompt() → Kling API (async) → download → cache
  → WebSocket経由でoverlay/video_bg.htmlに通知

プロバイダ抽象化:
  KlingProvider を差し替えることで他APIにも対応可能。
"""

import asyncio
import os
import time
import hashlib
import aiohttp
from typing import Optional
from dataclasses import dataclass
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)


@dataclass
class VideoResult:
    """動画生成結果"""
    url: str = ''           # リモートURL
    local_path: str = ''    # ローカルキャッシュパス
    topic: str = ''
    prompt: str = ''
    duration_sec: float = 5.0
    status: str = 'pending'  # pending / generating / ready / error


# --- プロンプト構築 ---

# まおの世界観に合うアニメスタイルの基本設定
STYLE_PREFIX = (
    "anime style, soft dreamy atmosphere, pastel colors, "
    "gentle lighting, looping seamless animation, "
    "ethereal and calming, Studio Ghibli inspired, "
    "no text, no people, no faces, "
)

STYLE_NEGATIVE = (
    "realistic, photographic, harsh lighting, "
    "text, watermark, logo, ugly, distorted, "
    "violent, scary, dark horror"
)

# 話題カテゴリ → ビジュアル描写のマッピング
TOPIC_VISUAL_MAP = {
    '宇宙': 'vast galaxy with nebula clouds and twinkling stars slowly drifting',
    '星': 'night sky full of stars with gentle shooting stars',
    '海': 'calm ocean waves under moonlight with soft reflections',
    '猫': 'cute anime cat sitting on a windowsill watching rain',
    '音楽': 'musical notes floating in a dreamy colorful space',
    '食べ物': 'beautiful anime food on a cozy table with warm light',
    '夜': 'peaceful anime cityscape at night with glowing windows',
    '朝': 'sunrise over anime countryside with morning mist',
    '雨': 'rain drops on a window with blurred city lights behind',
    '花': 'cherry blossom petals falling in slow motion',
    '夢': 'surreal floating islands in a pastel sky',
    '本': 'open book with magical particles rising from pages',
    '旅': 'anime train passing through a scenic mountain valley',
    '森': 'magical forest with soft sunlight filtering through leaves',
    '動画': 'retro TV set in a cozy room playing colorful static',
    '技術': 'holographic data streams flowing in a dark digital space',
    'AI': 'abstract neural network nodes pulsing with soft light',
    'ゲーム': 'pixel art world with floating platforms and clouds',
}

# デフォルトの抽象的なビジュアル
DEFAULT_VISUALS = [
    'soft abstract shapes morphing slowly in pastel colors',
    'gentle aurora lights dancing across a dark sky',
    'floating crystal orbs drifting in ethereal mist',
    'calm water surface with subtle ripples and reflections',
]

def build_video_prompt(topic: str, keywords: list = None) -> str:
    """話題とキーワードからビジュアルプロンプトを構築"""
    visual = None
    # キーワードからビジュアルを検索
    search_terms = [topic] + (keywords or [])
    for term in search_terms:
        for key, desc in TOPIC_VISUAL_MAP.items():
            if key in term:
                visual = desc
                break
        if visual:
            break
    # 見つからなければデフォルト
    if not visual:
        import random
        visual = random.choice(DEFAULT_VISUALS)
    return STYLE_PREFIX + visual


def _cache_key(prompt: str) -> str:
    """プロンプトからキャッシュファイル名を生成"""
    h = hashlib.md5(prompt.encode()).hexdigest()[:12]
    return f"video_{h}.mp4"

class KlingProvider:
    """
    Kling APIプロバイダ。
    PiAPI / aimlapi / 公式APIに対応（base_url差し替え）。
    """

    # プリセットプロバイダ設定
    PROVIDERS = {
        'piapi': {
            'base_url': 'https://api.piapi.ai/api/v1',
            'create_endpoint': '/task',
            'status_endpoint': '/task/{task_id}',
            'auth_header': 'x-api-key',
        },
        'aimlapi': {
            'base_url': 'https://api.aimlapi.com/v2',
            'create_endpoint': '/video/generations',
            'status_endpoint': '/video/generations',
            'auth_header': 'Authorization',
            'auth_prefix': 'Bearer ',
        },
        'kling_official': {
            'base_url': 'https://api.klingai.com/v1',
            'create_endpoint': '/videos/text2video',
            'status_endpoint': '/videos/text2video/{task_id}',
            'auth_header': 'Authorization',
            'auth_prefix': 'Bearer ',
        },
    }

    def __init__(self, provider: str = 'piapi', api_key: str = None):
        self.api_key = api_key or os.getenv('KLING_API_KEY', '')
        conf = self.PROVIDERS.get(provider, self.PROVIDERS['piapi'])
        self.base_url = conf['base_url']
        self.create_ep = conf['create_endpoint']
        self.status_ep = conf['status_endpoint']
        self.auth_header = conf['auth_header']
        self.auth_prefix = conf.get('auth_prefix', '')
        self.provider = provider

    def _headers(self) -> dict:
        return {
            self.auth_header: f'{self.auth_prefix}{self.api_key}',
            'Content-Type': 'application/json',
        }

    async def create_task(self, prompt: str, duration: int = 5,
                          aspect_ratio: str = '16:9',
                          negative_prompt: str = '') -> Optional[str]:
        """動画生成タスクを作成。タスクIDを返す。"""
        neg = negative_prompt or STYLE_NEGATIVE

        # プロバイダ別ペイロード
        if self.provider == 'piapi':
            payload = {
                'model': 'kling',
                'task_type': 'video_generation',
                'input': {
                    'prompt': prompt,
                    'negative_prompt': neg,
                    'cfg_scale': 0.5,
                    'duration': duration,
                    'aspect_ratio': aspect_ratio,
                    'mode': 'std',
                },
            }
        elif self.provider == 'aimlapi':
            payload = {
                'model': 'kling-video/v1/standard/text-to-video',
                'prompt': prompt,
                'negative_prompt': neg,
                'aspect_ratio': aspect_ratio,
                'duration': str(duration),
            }
        else:  # kling_official
            payload = {
                'prompt': prompt,
                'negative_prompt': neg,
                'cfg_scale': 0.5,
                'duration': str(duration),
                'aspect_ratio': aspect_ratio,
                'mode': 'std',
            }

        url = f'{self.base_url}{self.create_ep}'
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload,
                                        headers=self._headers(),
                                        timeout=aiohttp.ClientTimeout(total=30)
                                        ) as resp:
                    if resp.status >= 400:
                        err = await resp.text()
                        logger.error(f'Kling create_task failed: {resp.status} {err}')
                        return None
                    data = await resp.json()
            # タスクIDの取得（プロバイダ別）
            if self.provider == 'piapi':
                return data.get('data', {}).get('task_id', data.get('task_id'))
            elif self.provider == 'aimlapi':
                return data.get('id')
            else:
                return data.get('data', {}).get('task_id', data.get('task_id'))
        except Exception as e:
            logger.error(f'Kling create_task error: {e}')
            return None

    async def create_img2video_task(self, image_url: str,
                                     prompt: str = 'subtle natural movement, gentle wind, hair flowing, soft breathing, atmospheric',
                                     duration: int = 10) -> Optional[str]:
        """画像→動画変換タスクを作成（PiAPI専用）"""
        payload = {
            'model': 'kling',
            'task_type': 'video_generation',
            'input': {
                'prompt': prompt,
                'image_url': image_url,
                'duration': duration,
                'mode': 'std',
            },
        }
        url = f'{self.base_url}{self.create_ep}'
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload,
                                        headers=self._headers(),
                                        timeout=aiohttp.ClientTimeout(total=30)
                                        ) as resp:
                    if resp.status >= 400:
                        err = await resp.text()
                        logger.error(f'Kling img2video failed: {resp.status} {err[:200]}')
                        return None
                    data = await resp.json()
            return data.get('data', {}).get('task_id')
        except Exception as e:
            logger.error(f'Kling img2video error: {e}')
            return None

    async def poll_status(self, task_id: str) -> tuple[str, str]:
        """タスクの状態を確認。(status, video_url) を返す。"""
        if self.provider == 'aimlapi':
            url = f'{self.base_url}{self.status_ep}?generation_id={task_id}'
        else:
            url = f'{self.base_url}{self.status_ep}'.replace('{task_id}', task_id)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._headers(),
                                       timeout=aiohttp.ClientTimeout(total=15)
                                       ) as resp:
                    if resp.status >= 400:
                        return ('error', '')
                    data = await resp.json()

            # プロバイダ別のステータスと動画URL抽出
            if self.provider == 'piapi':
                status = data.get('data', {}).get('status', 'unknown')
                video_url = ''
                output = data.get('data', {}).get('output', {})
                if isinstance(output, dict):
                    video_url = output.get('video_url', '')
                elif isinstance(output, list) and output:
                    video_url = output[0] if isinstance(output[0], str) else ''
                done = status in ('completed', 'SUCCESS')
                return ('ready' if done else status, video_url)

            elif self.provider == 'aimlapi':
                status = data.get('status', 'unknown')
                video_url = data.get('video', {}).get('url', '') if data.get('video') else ''
                done = status == 'completed'
                return ('ready' if done else status, video_url)
            else:  # kling_official
                status = data.get('data', {}).get('status', 'unknown')
                videos = data.get('data', {}).get('response', [])
                video_url = videos[0] if videos else ''
                done = status in ('completed', 'SUCCESS')
                return ('ready' if done else status, video_url)

        except Exception as e:
            logger.error(f'Kling poll error: {e}')
            return ('error', '')

    async def download_video(self, url: str, filename: str) -> str:
        """動画をローカルキャッシュにダウンロード"""
        local_path = os.path.join(CACHE_DIR, filename)
        if os.path.exists(local_path):
            return local_path
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        with open(local_path, 'wb') as f:
                            f.write(await resp.read())
                        logger.info(f'Video downloaded: {local_path}')
                        return local_path
        except Exception as e:
            logger.error(f'Video download error: {e}')
        return ''

class VideoGenerator:
    """
    動画生成の統合マネージャ。
    topic_changeイベントを受けて非同期で動画を生成し、
    完了時にoverlay_server経由でBrowser Sourceに通知する。
    """

    def __init__(self, overlay_server=None,
                 provider: str = 'piapi',
                 api_key: str = None):
        self.overlay = overlay_server
        self.provider = KlingProvider(provider=provider, api_key=api_key)
        self._generating: dict = {}  # topic→task_id
        self._cache: dict = {}       # prompt_hash→local_path
        self._current_task: Optional[asyncio.Task] = None
        key = api_key or os.getenv('KLING_API_KEY', '')
        self._enabled = bool(key and not key.startswith('xxxx'))

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def on_topic_change(self, topic: str, keywords: list = None):
        """話題変更時に呼ばれる。動画生成を開始。"""
        if not self._enabled:
            return

        prompt = build_video_prompt(topic, keywords)
        cache_file = _cache_key(prompt)
        cache_path = os.path.join(CACHE_DIR, cache_file)

        # キャッシュヒット
        if os.path.exists(cache_path):
            logger.info(f'Video cache hit: {topic}')
            self._notify_video_ready(cache_path, topic)
            return

        # 前の生成タスクをキャンセル
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

        # 非同期で生成開始
        self._current_task = asyncio.create_task(
            self._generate_and_notify(prompt, cache_file, topic)
        )

    async def _generate_and_notify(self, prompt: str, cache_file: str,
                                    topic: str):
        """生成→ポーリング→ダウンロード→通知"""
        logger.info(f'Video generation started: {topic}')
        task_id = await self.provider.create_task(prompt)
        if not task_id:
            logger.warning(f'Video task creation failed: {topic}')
            return

        # ポーリング（最大5分）
        for _ in range(60):
            await asyncio.sleep(5)
            status, video_url = await self.provider.poll_status(task_id)
            if status == 'ready' and video_url:
                local = await self.provider.download_video(video_url, cache_file)
                if local:
                    logger.info(f'Video ready: {topic} -> {local}')
                    self._notify_video_ready(local, topic)
                    return
            elif status == 'error':
                logger.warning(f'Video generation error: {topic}')
                return
        logger.warning(f'Video generation timeout: {topic}')

    def _notify_video_ready(self, local_path: str, topic: str):
        """動画準備完了をoverlay_serverに通知"""
        if self.overlay and self.overlay.is_running:
            # file:///パスに変換（OBS Browser Source用）
            abs_path = os.path.abspath(local_path).replace('\\', '/')
            file_url = f'file:///{abs_path}'
            self.overlay.broadcast_topic_change(
                topic=topic,
                image_url=file_url,  # video URLとして再利用
            )
            # 専用の動画イベントも送信
            import json
            msg = {
                'type': 'video_ready',
                'timestamp': time.time(),
                'topic': topic,
                'video_url': file_url,
            }
            self.overlay._broadcast(msg)

    async def pregenerate_common(self, topics: list[dict]):
        """配信開始前に共通話題の動画をプリ生成"""
        if not self._enabled:
            return
        for t in topics[:5]:  # 最大5つ先読み
            topic = t.get('topic', '')
            keywords = t.get('keywords', [])
            prompt = build_video_prompt(topic, keywords)
            cache_file = _cache_key(prompt)
            cache_path = os.path.join(CACHE_DIR, cache_file)
            if not os.path.exists(cache_path):
                logger.info(f'Pre-generating video: {topic}')
                asyncio.create_task(
                    self._generate_and_notify(prompt, cache_file, topic)
                )
                await asyncio.sleep(1)  # API レートリミット回避

    def get_cached_count(self) -> int:
        """キャッシュ済み動画数"""
        return len([f for f in os.listdir(CACHE_DIR) if f.endswith('.mp4')])

    def clear_cache(self):
        """キャッシュをクリア"""
        import glob
        for f in glob.glob(os.path.join(CACHE_DIR, '*.mp4')):
            os.remove(f)
