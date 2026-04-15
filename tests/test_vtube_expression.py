# tests/test_vtube_expression.py
"""VTube Studio 表情変化の実機テスト（連続注入で変化を維持）"""

import asyncio
import json
import websockets


async def inject_loop(ws, params, duration=3.0, interval=0.1):
    """パラメータを連続注入して変化を維持する"""
    steps = int(duration / interval)
    for _ in range(steps):
        await ws.send(json.dumps({
            'apiName': 'VTubeStudioPublicAPI',
            'apiVersion': '1.0',
            'requestID': 'inj',
            'messageType': 'InjectParameterDataRequest',
            'data': {'parameterValues': params},
        }))
        await ws.recv()
        await asyncio.sleep(interval)


async def main():
    print('VTube Studio 表情テスト（連続注入版）')
    print('VTube Studioの画面を見ていてください！')
    print('='*50)

    async with websockets.connect('ws://localhost:8001') as ws:
        # 認証
        await ws.send(json.dumps({
            'apiName': 'VTubeStudioPublicAPI',
            'apiVersion': '1.0',
            'requestID': 'auth1',
            'messageType': 'AuthenticationTokenRequest',
            'data': {
                'pluginName': 'ExpressionTest',
                'pluginDeveloper': 'AIIdolProject',
            },
        }))
        auth_resp = json.loads(await ws.recv())
        token = auth_resp.get('data', {}).get('authenticationToken', '')
        if not token:
            print('トークン取得失敗')
            return

        await ws.send(json.dumps({
            'apiName': 'VTubeStudioPublicAPI',
            'apiVersion': '1.0',
            'requestID': 'auth2',
            'messageType': 'AuthenticationRequest',
            'data': {
                'pluginName': 'ExpressionTest',
                'pluginDeveloper': 'AIIdolProject',
                'authenticationToken': token,
            },
        }))
        auth2 = json.loads(await ws.recv())
        if not auth2.get('data', {}).get('authenticated'):
            print('認証失敗。VTube Studioで許可してください。')
            return
        print('認証OK\n')

        # テスト1: 大きく口を開ける
        print('[1/4] 口を大きく開ける（3秒）... ', end='', flush=True)
        await inject_loop(ws, [
            {'id': 'MouthOpen', 'value': 1.0},
        ], duration=3.0)
        print('done')

        await asyncio.sleep(1)

        # テスト2: 笑顔
        print('[2/4] 笑顔（3秒）... ', end='', flush=True)
        await inject_loop(ws, [
            {'id': 'MouthSmile', 'value': 1.0},
            {'id': 'EyeOpenLeft', 'value': 0.3},
            {'id': 'EyeOpenRight', 'value': 0.3},
        ], duration=3.0)
        print('done')

        await asyncio.sleep(1)

        # テスト3: 驚き（目見開き＋眉上げ＋口）
        print('[3/4] 驚き（3秒）... ', end='', flush=True)
        await inject_loop(ws, [
            {'id': 'EyeOpenLeft', 'value': 1.0},
            {'id': 'EyeOpenRight', 'value': 1.0},
            {'id': 'BrowLeftY', 'value': 1.0},
            {'id': 'BrowRightY', 'value': 1.0},
            {'id': 'MouthOpen', 'value': 0.6},
        ], duration=3.0)
        print('done')

        await asyncio.sleep(1)

        # テスト4: 顔を大きく横に振る
        print('[4/4] 顔を横に振る（3秒）... ', end='', flush=True)
        await inject_loop(ws, [
            {'id': 'FaceAngleX', 'value': 20.0},
        ], duration=1.5)
        await inject_loop(ws, [
            {'id': 'FaceAngleX', 'value': -20.0},
        ], duration=1.5)
        print('done')

        print('\n表情テスト完了！変化は見えましたか？')

asyncio.run(main())
