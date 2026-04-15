# video/image_generator.py
"""
AI映像生成 v3 - アイテムベースアーキテクチャ

部屋は「生きた空間」。アイテム（物）がある。
まおはアイテムと関わる。話題はアイテムの組み合わせ。
"""

import asyncio
import os
import hashlib
import json
import aiohttp
from typing import Optional
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

IMG_CACHE = os.path.join(os.path.dirname(__file__), 'cache', 'img')
os.makedirs(IMG_CACHE, exist_ok=True)
ROOM_STATE_PATH = os.path.join(os.path.dirname(__file__), 'room_state.json')
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), 'manifest.json')

# =====================================================
#  部屋の状態を読み込む
# =====================================================
def load_room_state():
    with open(ROOM_STATE_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

_room = load_room_state()

# =====================================================
#  永続設定
# =====================================================
STYLE = (
    "anime illustration, high quality, detailed, "
    "warm indoor lighting, soft shadows, atmospheric, "
    "no text, no UI, no watermark, masterpiece"
)

MAO_CHARACTER = (
    "a teenage anime girl with long gray-brown hair "
    "tied with red ribbons, wearing a cream cardigan "
    "over a navy sailor uniform with blue ribbon, "
    "gentle expression, soft features"
)

def build_room_description():
    """room_state.jsonから部屋の記述を自動生成"""
    layout = _room['layout']
    parts = [layout['camera']]
    parts.extend(layout['fixed'])
    for name, f in _room['furniture'].items():
        parts.append(f"{f['description']} ({f['position']})")
    for name, item in _room['items'].items():
        parts.append(f"{item['description']} ({item['position']})")
    return ', '.join(parts)

ROOM_DESCRIPTION = build_room_description()

CAM_A = (
    "close-up shot from front, looking directly at camera, "
    "face fills most of frame, shallow depth of field, "
    "intimate eye contact with viewer"
)
CAM_B = (
    "medium shot from three-quarter angle, "
    "upper body and surroundings visible, "
    "natural candid moment, not looking at camera"
)
CAM_C = (
    "wide establishing shot showing the whole room, "
    "girl is small in frame, atmospheric, cinematic"
)
CAM_MAP = {'A': CAM_A, 'B': CAM_B, 'C': CAM_C}

# =====================================================
#  プロンプト構築
# =====================================================
def build_clip_prompt(clip_data: dict) -> dict:
    """クリップデータからFlux/Klingプロンプトを生成"""
    cam = CAM_MAP.get(clip_data.get('cam', 'B'), CAM_B)
    action = clip_data['action']
    return {
        'image': f'{STYLE}, {cam}, {MAO_CHARACTER}, {action}, in {ROOM_DESCRIPTION}',
        'video': f'{action}, natural body movement, hair sways gently, smooth anime motion, cinematic',
    }

def get_all_clips():
    """全クリップ定義を返す（プリレンダー用）"""
    clips = []
    for name, f in _room['furniture'].items():
        for c in f['clips']:
            clips.append({**c, 'category': 'furniture', 'item': name})
    for name, item in _room['items'].items():
        for c in item['clips']:
            clips.append({**c, 'category': 'item', 'item': name})
    for c in _room['talking']:
        clips.append({**c, 'category': 'talking', 'item': '_talking'})
    for c in _room['transitions']:
        clips.append({**c, 'category': 'transition', 'item': '_transition'})
    for emo, c in _room['reactions'].items():
        clips.append({**c, 'category': 'reaction', 'item': emo})
    return clips

def get_topic_items(topic: str, keywords: list = None) -> list:
    """話題からアイテムリストを取得"""
    search = [topic] + (keywords or [])
    for term in search:
        for key, items in _room['topic_items'].items():
            if key in term:
                return items
    return _room.get('default_items', ['desk', 'mug'])

def get_item_clips(item_id: str) -> list:
    """アイテムのクリップ定義を取得"""
    if item_id in _room['furniture']:
        return _room['furniture'][item_id]['clips']
    if item_id in _room['items']:
        return _room['items'][item_id]['clips']
    return []

def get_item_keywords():
    """コメント検出用キーワードマップ"""
    return _room.get('item_keywords', {})

def _img_cache_key(prompt):
    return f'img_{hashlib.md5(prompt.encode()).hexdigest()[:12]}.png'

# =====================================================
#  FluxProvider（PiAPI画像生成）
# =====================================================
class FluxProvider:
    def __init__(self, api_key=None, model='Qubico/flux1-schnell'):
        self.api_key = api_key or os.getenv('KLING_API_KEY', '')
        self.model = model
        self.base_url = 'https://api.piapi.ai/api/v1'
    def _headers(self):
        return {'x-api-key': self.api_key, 'Content-Type': 'application/json'}
    async def create_task(self, prompt, width=1280, height=720):
        payload = {'model': self.model, 'task_type': 'txt2img',
                   'input': {'prompt': prompt, 'width': width, 'height': height}}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f'{self.base_url}/task', json=payload,
                                  headers=self._headers(),
                                  timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status >= 400: return None
                    data = await r.json()
            return data.get('data', {}).get('task_id')
        except Exception as e:
            logger.error(f'Flux create: {e}'); return None
    async def poll_status(self, task_id):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f'{self.base_url}/task/{task_id}',
                                 headers=self._headers(),
                                 timeout=aiohttp.ClientTimeout(total=15)) as r:
                    if r.status >= 400: return ('error', '')
                    data = await r.json()
            st = data.get('data', {}).get('status', 'unknown')
            url = ''
            out = data.get('data', {}).get('output', {})
            if isinstance(out, dict): url = out.get('image_url', '')
            elif isinstance(out, list) and out:
                url = out[0] if isinstance(out[0], str) else out[0].get('image_url', '')
            return ('ready' if st in ('completed', 'SUCCESS') else st, url)
        except Exception as e:
            logger.error(f'Flux poll: {e}'); return ('error', '')

    async def download_image(self, url, filename):
        path = os.path.join(IMG_CACHE, filename)
        if os.path.exists(path): return path
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status == 200:
                        with open(path, 'wb') as f: f.write(await r.read())
                        return path
        except Exception as e:
            logger.error(f'Img download: {e}')
        return ''

# =====================================================
#  ImageGenerator v3 - マニフェストからの即時ロード
# =====================================================
class ImageGenerator:
    def __init__(self, overlay_server=None, api_key=None):
        self.overlay = overlay_server
        key = api_key or os.getenv('KLING_API_KEY', '')
        self.provider = FluxProvider(api_key=key)
        self._enabled = bool(key and not key.startswith('xxxx'))
        self._manifest = self._load_manifest()

    @property
    def is_enabled(self): return self._enabled

    def _load_manifest(self):
        if os.path.exists(MANIFEST_PATH):
            try:
                with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}

    def get_cached_count(self):
        return len(self._manifest.get('clips', {}))

    async def on_topic_change(self, topic, keywords=None):
        """後方互換: pipeline.pyから呼ばれる"""
        pass
