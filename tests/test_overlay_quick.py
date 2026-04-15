# tests/test_overlay_quick.py
"""WebSocket経由でオーバーレイにテストイベントを送信"""
import asyncio
import json
import websockets

async def main():
    print('=== Overlay Quick Test ===')

    # 1. WebSocketサーバーを起動
    from broadcast.overlay_server import OverlayServer
    server = OverlayServer()
    await server.start()
    print('Server started (WS:8765, HTTP:8766)')
    await asyncio.sleep(2)
    print(f'Connected clients: {len(server._clients)}')

    # 2. 字幕テスト
    print('\n--- Subtitle test ---')
    server.broadcast_subtitle(
        text='これはテスト字幕です。次の字幕が来るまで消えません。',
        topic='テスト話題',
        phase='main',
    )
    print('Subtitle sent. Check OBS.')
    await asyncio.sleep(5)

    # 3. 動画テスト
    import os
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             'video', 'cache')
    mp4s = [f for f in os.listdir(cache_dir) if f.endswith('.mp4')]
    print(f'\n--- Video test ---')
    print(f'Available videos: {mp4s}')
    if mp4s:
        vid_file = mp4s[0]
        http_url = f'http://127.0.0.1:8766/video/cache/{vid_file}'
        print(f'Sending video_ready: {http_url}')
        msg = {'type': 'video_ready', 'topic': 'test', 'video_url': http_url}
        server._broadcast(msg)
        print('Video event sent. Check OBS - should show video.')
    else:
        print('No cached videos found. Run test_full_chain.py first.')

    # 4. HTTP配信確認
    if mp4s:
        import urllib.request
        try:
            req = urllib.request.Request(http_url, method='HEAD')
            resp = urllib.request.urlopen(req, timeout=3)
            print(f'HTTP check: {resp.status} ({resp.headers.get("Content-Length","?")} bytes)')
        except Exception as e:
            print(f'HTTP check FAILED: {e}')

    # 30秒待機してOBSで確認
    print('\n--- Waiting 30s for OBS check (Ctrl+C to stop) ---')
    try:
        await asyncio.sleep(30)
    except KeyboardInterrupt:
        pass

    await server.stop()
    print('Done.')

asyncio.run(main())
