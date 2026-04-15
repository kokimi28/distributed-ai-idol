# tests/test_video_api_live.py
"""
Kling API ライブテスト - 実際に動画を1本生成する
クレジットを消費するので注意
"""
import asyncio
import time
from video.video_generator import VideoGenerator, build_video_prompt, KlingProvider

async def main():
    print('=== Kling API Live Test ===')
    print()

    # プロンプト構築テスト
    topic = '宇宙の話'
    keywords = ['星', '銀河']
    prompt = build_video_prompt(topic, keywords)
    print(f'Topic: {topic}')
    print(f'Prompt: {prompt}')
    print()

    # VideoGenerator初期化
    vg = VideoGenerator()
    print(f'Enabled: {vg.is_enabled}')
    if not vg.is_enabled:
        print('ERROR: KLING_API_KEY not set or placeholder')
        return

    # タスク作成
    print('[1/3] Creating task...')
    start = time.time()
    task_id = await vg.provider.create_task(prompt, duration=5)
    if not task_id:
        print('ERROR: Task creation failed')
        print('Check: API key valid? Credits remaining?')
        return

    elapsed = time.time() - start
    print(f'  Task ID: {task_id}')
    print(f'  Created in {elapsed:.1f}s')
    print()

    # ポーリング
    print('[2/3] Polling for completion (this takes 60-120s)...')
    poll_start = time.time()
    video_url = ''
    for i in range(60):  # 最大5分
        await asyncio.sleep(5)
        status, url = await vg.provider.poll_status(task_id)
        elapsed = time.time() - poll_start
        print(f'  [{elapsed:.0f}s] status={status}')

        if status == 'ready' and url:
            video_url = url
            print(f'  Video URL: {url[:80]}...')
            break
        elif status == 'error':
            print('  ERROR: Generation failed')
            return

    if not video_url:
        print('  TIMEOUT: Video not ready after 5 minutes')
        return

    # ダウンロード
    print()
    print('[3/3] Downloading...')
    local = await vg.provider.download_video(video_url, 'test_space.mp4')
    if local:
        import os
        size = os.path.getsize(local)
        print(f'  Saved: {local}')
        print(f'  Size: {size/1024:.0f} KB')
    else:
        print('  ERROR: Download failed')
        return

    total = time.time() - start
    print()
    print(f'=== SUCCESS ===')
    print(f'Total time: {total:.0f}s')
    print(f'File: {local}')
    print(f'Open in browser to preview:')
    abs_path = os.path.abspath(local).replace("\\", "/")
    print(f'  file:///{abs_path}')

asyncio.run(main())
