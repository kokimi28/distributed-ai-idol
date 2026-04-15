"""
Flux Multi-Frame Generator v2
同じポーズで微表情だけ変えた3フレームを生成。
ポーズは固定 → クロスフェードでゴースティングしない。
"""
import asyncio, json, os, sys
sys.path.insert(0, 'C:\\Projects\\distributed-ai-idol')
from dotenv import load_dotenv
load_dotenv()
from video.image_generator import FluxProvider, IMG_CACHE, MANIFEST_PATH, ROOM_DESCRIPTION, STYLE, MAO_CHARACTER, CAM_A

async def gen_frame(flux, prompt, filename):
    tid = await flux.create_task(prompt)
    if not tid: return None
    for _ in range(20):
        await asyncio.sleep(3)
        st, url = await flux.poll_status(tid)
        if st == 'ready' and url:
            path = await flux.download_image(url, filename)
            return path
        if st == 'error': return None
    return None

# ===== v2: 同じポーズ、微表情だけ変化 =====
# 各フレームの差分は「目線」「口元」「頭の微傾き」だけ
BASE_POSE = {
    'talk_gesture': 'both hands gently clasped at chest level, facing camera',
    'talk_chin': 'chin resting on right hand, elbow on desk, facing camera',
    'talk_excited': 'leaning forward slightly, hands clasped together on desk',
    'talk_think': 'finger on chin, head slightly tilted, facing camera',
    'talk_laugh': 'hand lightly covering mouth, shoulders relaxed',
    'talk_whisper': 'leaning toward camera slightly, hand near mouth',
    'mug_sip': 'holding paw-print mug with both hands near face, steam rising',
    'cat_lap': 'orange cat curled in lap, one hand petting cat, other hand on desk',
    'desk_think': 'sitting at desk, chin on hand, laptop screen glowing',
}

# 微表情バリエーション（ポーズは変えない）
EXPRESSIONS = [
    'neutral relaxed expression, eyes looking at camera, mouth closed, calm',
    'soft smile, eyes slightly narrowed happily, mouth corners up, warm',
    'mouth slightly open as if talking, eyes bright, engaged expression',
]


async def main():
    key = os.getenv('KLING_API_KEY', '')
    flux = FluxProvider(api_key=key)
    manifest = json.load(open(MANIFEST_PATH, 'r', encoding='utf-8'))
    
    total = len(BASE_POSE) * len(EXPRESSIONS)
    print(f'{len(BASE_POSE)} clips x {len(EXPRESSIONS)} frames = {total} images (${total*0.003:.2f})')
    
    done = 0
    for clip_id, pose in BASE_POSE.items():
        print(f'\n=== {clip_id} ===')
        frame_paths = []
        for i, expr in enumerate(EXPRESSIONS):
            fname = f'mf2_{clip_id}_f{i}.png'
            fpath = os.path.join(IMG_CACHE, fname)
            if os.path.exists(fpath):
                print(f'  frame {i}: cached')
                frame_paths.append(fpath)
                continue
            # ポーズ固定 + 表情だけ変える
            prompt = f'{STYLE}, {CAM_A}, {MAO_CHARACTER}, {pose}, {expr}, in {ROOM_DESCRIPTION}'
            print(f'  frame {i}: generating...', end=' ', flush=True)
            path = await gen_frame(flux, prompt, fname)
            if path:
                print('OK')
                frame_paths.append(path)
                done += 1
            else:
                print('FAIL')
            await asyncio.sleep(1)
        
        # マニフェスト更新
        if frame_paths:
            if clip_id not in manifest.get('clips', {}):
                manifest['clips'][clip_id] = {}
            manifest['clips'][clip_id]['frames'] = frame_paths
            with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    print(f'\nDone: {done} new frames generated')

asyncio.run(main())
