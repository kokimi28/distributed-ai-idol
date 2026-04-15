# tests/preflight.py  配信前プリフライトチェック
"""配信開始前に全サービスの死活を確認する。"""

import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

PASS = '[OK]'
FAIL = '[NG]'
results = []


def check(name, ok, detail=''):
    results.append((name, ok))
    print(f'  {PASS if ok else FAIL} {name}' + (f' - {detail}' if detail else ''))
    return ok


async def run_preflight():
    print('='*50)
    print('preflight check')
    print('='*50)
    ok = True

    # 1. API keys
    print('\n[1/6] API keys')
    for key in ['ANTHROPIC_API_KEY', 'YOUTUBE_API_KEY']:
        val = os.getenv(key, '')
        v = bool(val) and not val.startswith('xxxx')
        if not check(key, v, 'set' if v else 'missing'):
            ok = False

    # 2. AivisSpeech
    print('\n[2/6] AivisSpeech')
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get('http://127.0.0.1:10101/speakers', timeout=5)
            speakers = resp.json()
            names = [s['name'] for s in speakers[:3]]
            check('AivisSpeech', resp.status_code == 200,
                  f'{len(speakers)} speakers: {", ".join(names)}...')
    except Exception as e:
        check('AivisSpeech', False, str(e)); ok = False

    # 3. Claude API
    print('\n[3/6] Claude API')
    try:
        import anthropic
        c = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        r = c.messages.create(model='claude-sonnet-4-6', max_tokens=30,
                              messages=[{'role':'user','content':'ping'}])
        check('Claude API', True, f'OK: {r.content[0].text[:30]}')
    except Exception as e:
        check('Claude API', False, str(e)); ok = False

    # 4. YouTube Data API
    print('\n[4/6] YouTube API')
    try:
        from googleapiclient.discovery import build
        yt = build('youtube', 'v3', developerKey=os.getenv('YOUTUBE_API_KEY'))
        r = yt.videoCategories().list(part='snippet', regionCode='JP').execute()
        check('YouTube API', 'items' in r, f'{len(r["items"])} categories')
    except Exception as e:
        check('YouTube API', False, str(e)); ok = False

    # 5. Zep Cloud
    print('\n[5/6] Zep Cloud')
    try:
        from memory.zep_client import ZepMemory, ZEP_AVAILABLE
        if not ZEP_AVAILABLE:
            check('Zep SDK', False, 'not installed'); ok = False
        else:
            mem = ZepMemory()
            zok = await mem.initialize()
            check('Zep Cloud', zok, 'connected' if zok else 'failed')
            if not zok: ok = False
    except Exception as e:
        check('Zep Cloud', False, str(e)); ok = False

    # 6. Overlay + Image/Video pipeline
    print('\n[6/6] Visual pipeline')
    try:
        from broadcast.overlay_server import OverlayServer
        check('OverlayServer', True)
    except Exception as e:
        check('OverlayServer', False, str(e)); ok = False

    overlay_files = ['overlay/subtitle.html', 'overlay/main_visual.html', 'overlay/aurora.html']
    base = 'C:\\Projects\\distributed-ai-idol'
    for f in overlay_files:
        p = os.path.join(base, f)
        check(f, os.path.exists(p), 'OK' if os.path.exists(p) else 'missing')

    try:
        from video.image_generator import ImageGenerator
        ig = ImageGenerator()
        check('ImageGenerator', ig.is_enabled,
              'enabled' if ig.is_enabled else 'API key missing')
    except Exception as e:
        check('ImageGenerator', False, str(e)); ok = False

    # summary
    print('\n' + '='*50)
    passed = sum(1 for _, o in results if o)
    total = len(results)
    if ok:
        print(f'{PASS} all passed ({passed}/{total}) - ready')
    else:
        failed = [n for n, o in results if not o]
        print(f'{FAIL} failed ({passed}/{total}): {", ".join(failed)}')
    print('='*50)
    return ok


if __name__ == '__main__':
    r = asyncio.run(run_preflight())
    exit(0 if r else 1)
