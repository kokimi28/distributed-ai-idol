# video/prerender.py
"""
プリレンダリング v3 - アイテムベース

room_state.jsonの全クリップをプリレンダーする。
各クリップは固有ID(clip_id)で管理。

使い方:
  python -m video.prerender              # 未生成のみ
  python -m video.prerender --status     # 進捗確認
  python -m video.prerender --item cat   # 特定アイテムのみ
"""

import asyncio, argparse, json, os, time, sys, hashlib
from loguru import logger
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from video.image_generator import (
    get_all_clips, build_clip_prompt, FluxProvider,
    _img_cache_key, IMG_CACHE, MANIFEST_PATH,
)
from video.video_generator import KlingProvider, CACHE_DIR as VID_CACHE

def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'clips': {}}

def save_manifest(m):
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

def show_status():
    m = load_manifest()
    all_clips = get_all_clips()
    done = 0
    for c in all_clips:
        cid = c['id']
        entry = m.get('clips', {}).get(cid, {})
        if entry.get('video') and os.path.exists(entry['video']):
            done += 1
    total = len(all_clips)
    by_cat = {}
    for c in all_clips:
        cat = c['category']
        by_cat.setdefault(cat, [0, 0])
        by_cat[cat][1] += 1
        cid = c['id']
        entry = m.get('clips', {}).get(cid, {})
        if entry.get('video') and os.path.exists(entry['video']):
            by_cat[cat][0] += 1
    print(f'Total: {done}/{total} clips')
    for cat, (d, t) in sorted(by_cat.items()):
        print(f'  {cat}: {d}/{t}')

async def gen_flux(flux, prompt, cache_file):
    tid = await flux.create_task(prompt)
    if not tid: return None
    for _ in range(20):
        await asyncio.sleep(3)
        st, url = await flux.poll_status(tid)
        if st == 'ready' and url:
            await flux.download_image(url, cache_file)
            return url
        elif st == 'error': return None
    return None

async def gen_kling(kling, img_url, vid_prompt, vid_file, max_retries=2):
    vp = os.path.join(VID_CACHE, vid_file)
    if os.path.exists(vp): return vp
    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait = 10 * attempt
            logger.info(f'  Retry {attempt} after {wait}s')
            await asyncio.sleep(wait)
        tid = await kling.create_img2video_task(
            image_url=img_url, prompt=vid_prompt, duration=5)
        if not tid: continue
        for i in range(60):
            await asyncio.sleep(5)
            st, url = await kling.poll_status(tid)
            if i % 6 == 0: logger.info(f'  [{i*5}s] {st}')
            if st == 'ready' and url:
                return await kling.download_video(url, vid_file)
            elif st == 'error':
                break
    return None

async def render_clip(clip, flux, kling, manifest):
    """1クリップを生成（画像があればKlingだけ、なければFlux→Kling）"""
    cid = clip['id']
    if 'clips' not in manifest:
        manifest['clips'] = {}
    entry = manifest['clips'].get(cid, {})
    if entry.get('video') and os.path.exists(entry['video']):
        return True

    prompts = build_clip_prompt(clip)
    cf = _img_cache_key(prompts['image'])
    vf = f'{cid}.mp4'

    # 既存のimage_urlがあればFluxスキップ
    img_url = entry.get('image_url', '')
    if not img_url:
        logger.info(f'[flux] {cid}')
        img_url = await gen_flux(flux, prompts['image'], cf)
        if not img_url:
            logger.error(f'[flux] {cid} FAIL'); return False

    # Kling
    logger.info(f'[kling] {cid}')
    local = await gen_kling(kling, img_url, prompts['video'], vf)
    if local:
        if cid not in manifest['clips']:
            manifest['clips'][cid] = {}
        manifest['clips'][cid]['video'] = local
        if not manifest['clips'][cid].get('image'):
            manifest['clips'][cid]['image'] = os.path.join(IMG_CACHE, cf)
        manifest['clips'][cid]['item'] = clip.get('item', '')
        manifest['clips'][cid]['category'] = clip.get('category', '')
        manifest['clips'][cid]['cam'] = clip.get('cam', 'B')
        if img_url and not manifest['clips'][cid].get('image_url'):
            manifest['clips'][cid]['image_url'] = img_url
        save_manifest(manifest)
        logger.info(f'[done] {cid} OK')
        return True
    logger.error(f'[kling] {cid} FAIL')
    return False

async def run(args):
    key = os.getenv('KLING_API_KEY', '')
    flux = FluxProvider(api_key=key)
    kling = KlingProvider(provider='piapi', api_key=key)
    manifest = load_manifest()

    if args.status:
        show_status(); return

    all_clips = get_all_clips()

    # フィルタ
    if args.item:
        all_clips = [c for c in all_clips if c.get('item') == args.item]
    if args.category:
        all_clips = [c for c in all_clips if c.get('category') == args.category]

    # 未生成のみ
    todo = []
    for c in all_clips:
        entry = manifest.get('clips', {}).get(c['id'], {})
        if not (entry.get('video') and os.path.exists(entry['video'])):
            todo.append(c)

    if not todo:
        print('All clips are rendered!')
        show_status(); return

    print(f'{len(todo)} clips to render')
    start = time.time()
    done = 0
    for i, clip in enumerate(todo):
        print(f'\n=== [{i+1}/{len(todo)}] {clip["id"]} ({clip["category"]}/{clip["item"]}) ===')
        ok = await render_clip(clip, flux, kling, manifest)
        if ok: done += 1
        if i < len(todo) - 1:
            await asyncio.sleep(3)
    elapsed = time.time() - start
    print(f'\nDone: {done}/{len(todo)} in {elapsed/60:.1f} min')
    show_status()

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--status', action='store_true')
    p.add_argument('--item', type=str, help='Specific item')
    p.add_argument('--category', type=str, help='Category filter')
    asyncio.run(run(p.parse_args()))
