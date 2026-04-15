# tests/test_http_server.py
import asyncio
import urllib.request
from broadcast.overlay_server import OverlayServer

async def test():
    s = OverlayServer()
    await s.start()
    await asyncio.sleep(1)
    
    files = [
        ('Video', 'http://127.0.0.1:8766/chain_test.mp4'),
        ('Image', 'http://127.0.0.1:8766/img/chain_test.png'),
    ]
    for name, url in files:
        try:
            req = urllib.request.Request(url, method='HEAD')
            resp = urllib.request.urlopen(req, timeout=3)
            size = resp.headers.get('Content-Length', '?')
            print(f'{name}: HTTP {resp.status} ({int(size)//1024}KB)')
        except Exception as e:
            print(f'{name}: {e}')
    
    await s.stop()
    print('HTTP server test done')

asyncio.run(test())
