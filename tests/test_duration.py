import asyncio, os, aiohttp, sys
sys.path.insert(0, 'C:\\Projects\\distributed-ai-idol')
from dotenv import load_dotenv
load_dotenv('C:\\Projects\\distributed-ai-idol\\.env')
from video.image_generator import FluxProvider
key = os.getenv('KLING_API_KEY','')
headers = {'x-api-key': key, 'Content-Type': 'application/json'}

async def main():
    flux = FluxProvider(api_key=key)
    tid = await flux.create_task('anime girl, cozy room')
    if not tid: print('Flux fail'); return
    img_url = None
    for _ in range(15):
        await asyncio.sleep(3)
        st, url = await flux.poll_status(tid)
        if st == 'ready' and url: img_url = url; break
    if not img_url: print('Flux timeout'); return
    print(f'Image: {img_url}')
    # Full Kling error
    p = {'model':'kling','task_type':'video_generation',
         'input':{'prompt':'girl waves','image_url':img_url,
                  'duration':5,'mode':'std'}}
    async with aiohttp.ClientSession() as s:
        async with s.post('https://api.piapi.ai/api/v1/task',
                          json=p, headers=headers) as r:
            full = await r.text()
            print(f'HTTP: {r.status}')
            print(f'FULL RESPONSE:')
            print(full)

asyncio.run(main())
