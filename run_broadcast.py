# run_broadcast.py
"""
配信ランチャー

Usage:
  python run_broadcast.py                    # 通常起動（YouTube Chat自動検出）
  python run_broadcast.py --no-youtube       # YouTube Chatなし（ローカルテスト）
  python run_broadcast.py --chat-id=XXXXX    # liveChatId直接指定
  python run_broadcast.py --duration=30      # 30分配信

Ctrl+C で停止。
"""

import asyncio
import argparse
import signal
import sys
import os

from dotenv import load_dotenv
load_dotenv()

from broadcast.pipeline import BroadcastPipeline, PipelineConfig
from llm.claude_bridge import ClaudeBridge
from brain.topic_generator import generate_topics
from shared.config_store import config as config_store
from shared.smart_picker import picker
from loguru import logger

# ── ログ設定 ──

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
    level="INFO",
)
logger.add(
    "logs/broadcast_{time:YYYYMMDD_HHmmss}.log",
    format="{time:HH:mm:ss.SSS} | {level:<7} | {module}:{function}:{line} | {message}",
    level="DEBUG",
    rotation="50 MB",
)


async def main(args):
    print('='*50)
    print('分散AIアイドル 配信ランチャー')
    print('='*50)

    # ── Step 0: 設定データプリロード ──
    print('\n[0/4] 設定データをプリロード中...')
    await config_store.preload([
        'fillers', 'reflex_rules', 'emotion_half_lives',
        'heat_rules', 'phase_instructions', 'voice_settings',
        'topic_fallbacks', 'vtube_params',
    ])
    print('  設定データ読み込み完了')

    # SmartPicker: 正規表現プリコンパイル
    picker.warmup()
    print('  SmartPicker warmup完了')

    # ── v3: プリレンダー済みキャッシュは保持。セッション画像のみクリア ──
    # 画像・動画はprerender.pyで生成済みなのでクリアしない
    print('  Cache: preserved (prerendered clips)')
    # manifest.jsonは保持（プリレンダー済みクリップ情報）

    # ── Step 1: 話題リスト生成 ──
    print('\n[1/4] 話題リストを生成中...')
    try:
        topics = generate_topics()
        logger.info(f'話題 {len(topics)}件 生成完了')
        for i, t in enumerate(topics[:5]):
            title = t.get('topic', t.get('title', ''))
            print(f'  {i+1}. {title}')
        if len(topics) > 5:
            print(f'  ... 他{len(topics)-5}件')
    except Exception as e:
        logger.warning(f'話題生成失敗（フォールバック使用）: {e}')
        topics = [
            {'topic': 'みんな寝る前になに見てる？', 'keywords': ['寝る前', '動画'], 'priority': 80},
            {'topic': 'もし味覚あったら最初なに食べる', 'keywords': ['味覚', '想像'], 'priority': 70},
            {'topic': '猫の動画やばくない？', 'keywords': ['猫', '動画'], 'priority': 60},
        ]
        print(f'  フォールバック話題 {len(topics)}件 を使用')

    # ── Step 2: ブリッジ・パイプライン構築 ──
    print('\n[2/4] パイプライン構築中...')

    bridge = ClaudeBridge(mode='broadcast')

    config = PipelineConfig(
        planned_duration_minutes=args.duration,
        prefer_voice_engine=args.engine,
        enable_vtube=not args.no_vtube,
        enable_youtube_chat=not args.no_youtube,
        youtube_live_chat_id=args.chat_id,
        initial_topics=topics,
        mode='broadcast',
        min_speak_interval=0.5,   # 最短発話間隔（秒）LLM+合成で自然に間が空く
        max_silence=3.0,          # 最長沈黙（秒）
    )

    pipeline = BroadcastPipeline(config, bridge.generate)

    # 感情状態の参照をブリッジに渡す
    bridge.set_char_state_ref(pipeline.char_state)

    # 発話コールバック（ログ出力）
    def on_speak(action, result):
        src = action.source if hasattr(action, 'source') else '?'
        logger.info(f'[{src}] {action.text}')
        print(f'\n  🎤 {action.text}')

    pipeline.on_speak_callback = on_speak

    # ── Step 3: 起動 ──
    print('\n[3/4] パイプライン起動...')
    status = await pipeline.start()

    print(f'  音声: {status["voice_engine"]}')
    print(f'  VTube: {"接続OK" if status["vtube_connected"] else "未接続（表情なし）"}')
    print(f'  話題: {status["topics_loaded"]}件')
    print(f'  YouTube Chat: {"接続OK" if status.get("youtube_chat") else "OFF"}')
    print(f'  Zep Memory: {"接続OK" if status.get("zep_memory") else "OFF（記憶なし）"}')
    print(f'  Overlay: {"ws://127.0.0.1:8765" if status.get("overlay") else "OFF"}')
    print(f'  AI Video: {"ON" if status.get("video_gen") else "OFF (KLING_API_KEY not set)"}')

    # ── Step 4: 配信ループ ──
    print(f'\n[4/4] 配信開始！（{args.duration}分予定）')
    print('  Ctrl+C で停止')
    print('='*50 + '\n')

    # Ctrl+Cでgraceful shutdown
    stop_event = asyncio.Event()

    def signal_handler():
        print('\n\n停止中...')
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: signal_handler())

    # ステータス表示ループ（30秒ごと）+ 自動終了検知（5秒ごと）
    async def status_ticker():
        tick_count = 0
        while not stop_event.is_set():
            await asyncio.sleep(5)
            tick_count += 1
            if stop_event.is_set():
                return
            # 配信終了を検知（autonomous_talkがclock.stop()した場合）
            if not pipeline.clock.is_live and pipeline._is_running:
                logger.info('[自動終了] 配信が終了しました')
                stop_event.set()
                return
            # 30秒ごと（5秒×6回）にステータス表示
            if tick_count % 6 != 0:
                continue
            s = pipeline.get_status()
            clock = s.get('clock', {})
            elapsed = clock.get('elapsed_min', 0)
            phase = clock.get('phase', '?')
            fatigue = s['char_state'].get('fatigue', 0)
            queue = s.get('comment_queue_size', 0)
            topic_info = s.get('topic', {})
            active_topic = 'なし'
            if isinstance(topic_info, dict):
                active_data = topic_info.get('active', {})
                if isinstance(active_data, dict):
                    active_topic = active_data.get('topic', 'なし') or 'なし'
            logger.info(
                f'[状態] {elapsed:.0f}分経過 | phase={phase} | '
                f'fatigue={fatigue} | queue={queue} | topic={active_topic} | '
                f'zep={"ON" if s.get("zep_memory_active") else "OFF"}'
            )

    ticker_task = asyncio.create_task(status_ticker())

    # 停止待ち
    await stop_event.wait()

    # ── 停止処理 ──
    ticker_task.cancel()
    try:
        await ticker_task
    except asyncio.CancelledError:
        pass

    result = await pipeline.stop()
    print(f'\n配信終了')
    print(f'  最終感情: {result["final_emotions"]}')
    if pipeline._zep._thread_id is None and pipeline._zep.is_enabled:
        print(f'  Zep: セッション保存済み')
    print('='*50)

    # ★pyaudio/AivisSpeechのネイティブリソースをクリーンアップ
    # 終了時のメモリアクセス違反を防止
    import gc
    gc.collect()
    await asyncio.sleep(0.5)
    os._exit(0)  # ネイティブライブラリのクラッシュを回避


def parse_args():
    parser = argparse.ArgumentParser(description='分散AIアイドル 配信ランチャー')
    parser.add_argument('--duration', type=float, default=60.0,
                        help='配信予定時間（分）デフォルト: 60')
    parser.add_argument('--no-youtube', action='store_true',
                        help='YouTube Chatポーリングを無効化')
    parser.add_argument('--no-vtube', action='store_true',
                        help='VTube Studio接続を無効化')
    parser.add_argument('--chat-id', type=str, default=None,
                        help='YouTube liveChatIdを直接指定')
    parser.add_argument('--engine', type=str, default='aivispeech',
                        choices=['aivispeech', 'elevenlabs'],
                        help='音声エンジン: aivispeech(デフォルト) or elevenlabs')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    os.makedirs('logs', exist_ok=True)

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print('\n強制停止')