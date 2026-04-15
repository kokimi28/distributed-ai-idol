import asyncio, os, sys
sys.path.insert(0, 'C:\\Projects\\distributed-ai-idol')
from dotenv import load_dotenv
load_dotenv()
import aiohttp, json

async def test():
    key = os.getenv('KLING_API_KEY')
    # Use a public test image
    test_url = 'https://img.theapi.app/temp/dfdf8223-b141-46a9-895f-f674404a4157.png'
    
    # Try different configs
    for mode in ['std', 'pro']:
        for dur in [5, 10]:
            payload = {
                'model': 'kling',
                'task_type': 'video_generation',
                'input': {
                    'prompt': 'subtle natural movement',
                    'image_url': test_url,
                    'duration': dur,
                    'mode': mode,
                },
            }
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    'https://api.piapi.ai/api/v1/task',
                    json=payload,
                    headers={'X-API-Key': key, 'Content-Type': 'application/json'},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as r:
                    status = r.status
                    text = await r.text()
                    d = json.loads(text)
                    task_status = d.get('data',{}).get('status','?')
                    print(f'mode={mode} dur={dur} → HTTP {status} task={task_status}')
                    if status < 400:
                        print(f'  task_id: {d.get("data",{}).get("task_id","")}')

asyncio.run(test())
