# tests/test_image_api_live.py
"""Flux API ライブテスト - 実際に画像を1枚生成"""
import asyncio
import time
from video.image_generator import ImageGenerator, build_image_prompt

async def main():
    print('=== Flux Image API Live Test ===')
    topic = '宇宙の話'
    prompt = build_image_prompt(topic, ['星', '銀河'])
    print(f'Topic: {topic}')
    print(f'Prompt: {prompt[:100]}...')
    ig = ImageGenerator()
    print(f'Enabled: {ig.is_enabled}')
    if not ig.is_enabled:
        print('ERROR: API key not set')
        return
    print('Creating task...')
    start = time.time()
    task_id = await ig.provider.create_task(prompt)
    if not task_id:
        print('ERROR: Task creation failed')
        return
    print(f'Task ID: {task_id} ({time.time()-start:.1f}s)')
    print('Polling...')
    for i in range(20):
        await asyncio.sleep(3)
        status, url = await ig.provider.poll_status(task_id)
        print(f'  [{(time.time()-start):.0f}s] {status}')
        if status == 'ready' and url:
            local = await ig.provider.download_image(url, 'test_space.png')
            if local:
                import os
                sz = os.path.getsize(local)
                print(f'=== SUCCESS ===')
                print(f'Time: {time.time()-start:.0f}s')
                print(f'File: {local} ({sz//1024}KB)')
                abs_p = os.path.abspath(local).replace('\\','/')
                print(f'Preview: file:///{abs_p}')
            return
        elif status == 'error':
            print('ERROR'); return
    print('TIMEOUT')

asyncio.run(main())
