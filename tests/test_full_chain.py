# tests/test_full_chain.py
"""Flux画像 → Kling動画 フルチェーンテスト"""
import asyncio, time, os
from video.image_generator import ImageGenerator, build_image_prompt

async def main():
    print('=== Full Chain Test: Flux Image -> Kling Video ===')
    ig = ImageGenerator()
    if not ig.is_enabled:
        print('ERROR: API key not set'); return

    topic = 'ゲームの話'
    prompt = build_image_prompt(topic, ['ゲーム'])
    print(f'Topic: {topic}')
    print(f'Prompt: {prompt[:80]}...')
    print(f'Video chain enabled: {ig._enable_video_chain}')
    print()

    # Phase 1: Flux画像生成
    print('[1/2] Flux image generation...')
    start = time.time()
    tid = await ig.provider.create_task(prompt)
    if not tid:
        print('ERROR: Flux task failed'); return
    print(f'  Task: {tid}')
    img_url_remote = ''
    for i in range(20):
        await asyncio.sleep(3)
        st, url = await ig.provider.poll_status(tid)
        elapsed = time.time() - start
        print(f'  [{elapsed:.0f}s] {st}')
        if st == 'ready' and url:
            img_url_remote = url
            local = await ig.provider.download_image(url, 'chain_test.png')
            if local:
                sz = os.path.getsize(local)
                print(f'  Image OK: {sz//1024}KB')
            break
        elif st == 'error':
            print('  ERROR'); return
    if not img_url_remote:
        print('  TIMEOUT'); return

    # Phase 2: Kling image-to-video
    print()
    print('[2/2] Kling image-to-video...')
    vid_prompt = None
    from video.image_generator import VIDEO_ACTION_PROMPTS, DEFAULT_VIDEO_PROMPT
    for key, prompt in VIDEO_ACTION_PROMPTS.items():
        if key in topic:
            vid_prompt = prompt
            break
    if not vid_prompt:
        vid_prompt = DEFAULT_VIDEO_PROMPT
    print(f'  Video action: {vid_prompt[:60]}...')
    phase2_start = time.time()
    vid_tid = await ig._kling.create_img2video_task(
        image_url=img_url_remote, prompt=vid_prompt, duration=10
    )
    if not vid_tid:
        print('  ERROR: Kling task failed'); return
    print(f'  Task: {vid_tid}')
    for i in range(60):
        await asyncio.sleep(5)
        st, vid_url = await ig._kling.poll_status(vid_tid)
        elapsed = time.time() - phase2_start
        print(f'  [{elapsed:.0f}s] {st}')
        if st == 'ready' and vid_url:
            local = await ig._kling.download_video(vid_url, 'chain_test.mp4')
            if local:
                sz = os.path.getsize(local)
                total = time.time() - start
                print(f'  Video OK: {sz//1024}KB')
                print(f'\n=== FULL CHAIN SUCCESS ===')
                print(f'  Image: {time.time()-start-elapsed:.0f}s')
                print(f'  Video: {elapsed:.0f}s')
                print(f'  Total: {total:.0f}s')
                ap = os.path.abspath(local).replace('\\','/')
                print(f'  file:///{ap}')
            return
        elif st == 'error':
            print('  ERROR'); return
    print('  TIMEOUT')

asyncio.run(main())
