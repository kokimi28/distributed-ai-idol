# tests/test_image_mao.py
"""Flux: まお一体型画像生成テスト"""
import asyncio, time, os
from video.image_generator import ImageGenerator, build_image_prompt

async def main():
    print('=== Mao Character Image Test ===')
    ig = ImageGenerator()
    if not ig.is_enabled:
        print('ERROR: API key not set'); return

    scenes = [
        ('猫の話', ['猫', '寝る']),
        ('深夜の思考', ['深夜']),
    ]
    for topic, kws in scenes:
        prompt = build_image_prompt(topic, kws)
        has_mao = 'gray-brown hair' in prompt
        print(f'\n--- {topic} ---')
        print(f'Has Mao: {has_mao}')
        print(f'Prompt: {prompt[:100]}...')
        start = time.time()
        tid = await ig.provider.create_task(prompt)
        if not tid:
            print('Task failed'); continue
        print(f'Task: {tid}')

        for i in range(20):
            await asyncio.sleep(3)
            st, url = await ig.provider.poll_status(tid)
            elapsed = time.time() - start
            print(f'  [{elapsed:.0f}s] {st}')
            if st == 'ready' and url:
                fname = f'test_mao_{topic[:4]}.png'
                local = await ig.provider.download_image(url, fname)
                if local:
                    sz = os.path.getsize(local)
                    ap = os.path.abspath(local).replace('\\', '/')
                    print(f'  OK: {sz//1024}KB')
                    print(f'  file:///{ap}')
                break
            elif st == 'error':
                print('  ERROR'); break

    print('\n=== Done ===')

asyncio.run(main())
