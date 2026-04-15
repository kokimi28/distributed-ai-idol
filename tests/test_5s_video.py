"""
Kling 5秒動画テスト
既存のFlux画像からKling image-to-videoで5秒動画を生成。
ピンポン再生で10秒に拡張 → 実質コスト半減。
"""
import asyncio, json, os, sys
sys.path.insert(0, 'C:\\Projects\\distributed-ai-idol')
from dotenv import load_dotenv
load_dotenv()
from video.video_generator import KlingProvider
from video.image_generator import IMG_CACHE, MANIFEST_PATH

async def test_5s_video():
    key = os.getenv('KLING_API_KEY', '')
    kling = KlingProvider(provider='piapi', api_key=key)
    
    # マニフェストから画像URLを取得（talk_gesture）
    manifest = json.load(open(MANIFEST_PATH, 'r', encoding='utf-8'))
    clip = manifest['clips'].get('talk_gesture', {})
    img_url = clip.get('image_url', '')
    
    if not img_url:
        print('ERROR: talk_gesture has no image_url in manifest')
        return
    
    print(f'Image URL: {img_url[:60]}...')
    print(f'Generating 5s Kling video...')
    
    # 5秒で生成
    tid = await kling.create_img2video_task(
        image_url=img_url,
        prompt='girl talking to camera with natural gestures, subtle head movement, blinking, hair sway, warm smile, anime style, smooth motion',
        duration=5,  # ★5秒
    )

    if not tid:
        print('ERROR: Failed to create task')
        return
    
    print(f'Task ID: {tid}')
    print('Polling...')
    
    for i in range(60):
        await asyncio.sleep(5)
        st, url = await kling.poll_status(tid)
        if i % 6 == 0:
            print(f'  [{i*5}s] {st}')
        if st == 'ready' and url:
            print(f'\nVideo URL: {url[:80]}...')
            vf = 'talk_gesture.mp4'
            path = await kling.download_video(url, vf)
            if path:
                size = os.path.getsize(path)
                print(f'Downloaded: {path} ({size/1024:.0f}KB)')
                # マニフェスト更新
                manifest['clips']['talk_gesture']['video'] = path
                with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)
                print('Manifest updated with video path')
            return
        elif st == 'error':
            print('ERROR: Generation failed')
            return
    print('TIMEOUT')

asyncio.run(test_5s_video())
