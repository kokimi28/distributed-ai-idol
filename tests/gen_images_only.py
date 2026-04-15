"""
v3クリップの静止画だけ先に生成する。
Flux画像は1枚$0.003。51枚で$0.15。
Kling動画はクレジット追加後に別途生成。
"""
import asyncio, json, os, sys, time
sys.path.insert(0, 'C:\\Projects\\distributed-ai-idol')
from video.image_generator import (
    get_all_clips, build_clip_prompt, FluxProvider,
    _img_cache_key, IMG_CACHE, MANIFEST_PATH,
)

async def gen_image(flux, prompt, filename):
    tid = await flux.create_task(prompt)
    if not tid: return None
    for _ in range(20):
        await asyncio.sleep(3)
        st, url = await flux.poll_status(tid)
        if st == 'ready' and url:
            path = await flux.download_image(url, filename)
            return url, path
        if st == 'error': return None
    return None

async def main():
    key = os.getenv('KLING_API_KEY', '')
    flux = FluxProvider(api_key=key)
    clips = get_all_clips()

    # マニフェスト読込
    with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    # 画像未生成のクリップだけ対象
    todo = []
    for c in clips:
        cid = c['id']
        entry = manifest.get('clips', {}).get(cid, {})
        img = entry.get('image', '')
        if not img or not os.path.exists(img):
            todo.append(c)

    print(f'{len(todo)} images to generate (${len(todo)*0.003:.2f})')
    if not todo:
        print('All done!'); return

    done = 0
    for i, clip in enumerate(todo):
        cid = clip['id']
        prompts = build_clip_prompt(clip)
        cf = _img_cache_key(prompts['image'])
        print(f'[{i+1}/{len(todo)}] {cid}...', end=' ', flush=True)
        result = await gen_image(flux, prompts['image'], cf)
        if result:
            url, path = result
            # マニフェスト更新（画像のみ、動画は後で）
            if cid not in manifest.get('clips', {}):
                manifest['clips'][cid] = {}
            manifest['clips'][cid]['image'] = path
            manifest['clips'][cid]['item'] = clip.get('item', '')
            manifest['clips'][cid]['category'] = clip.get('category', '')
            manifest['clips'][cid]['cam'] = clip.get('cam', 'B')
            manifest['clips'][cid]['image_url'] = url
            with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            done += 1
            print('OK')
        else:
            print('FAIL')
        await asyncio.sleep(1)
    print(f'\nDone: {done}/{len(todo)} images')

asyncio.run(main())
