# tests/check_vtube_params.py
"""VTube Studioのモデル情報とパラメータ一覧を取得し、表情注入テスト"""

import asyncio
import json
import websockets


async def check_vtube():
    print('VTube Studio パラメータ確認')
    print('='*50)

    async with websockets.connect('ws://localhost:8001') as ws:
        # 1. 認証
        print('[認証中...]')
        await ws.send(json.dumps({
            'apiName': 'VTubeStudioPublicAPI',
            'apiVersion': '1.0',
            'requestID': 'auth1',
            'messageType': 'AuthenticationTokenRequest',
            'data': {
                'pluginName': 'ParamChecker',
                'pluginDeveloper': 'AIIdolProject',
            },
        }))
        auth_resp = json.loads(await ws.recv())
        token = auth_resp.get('data', {}).get('authenticationToken', '')

        if not token:
            print('❌ トークン取得失敗')
            return
        await ws.send(json.dumps({
            'apiName': 'VTubeStudioPublicAPI',
            'apiVersion': '1.0',
            'requestID': 'auth2',
            'messageType': 'AuthenticationRequest',
            'data': {
                'pluginName': 'ParamChecker',
                'pluginDeveloper': 'AIIdolProject',
                'authenticationToken': token,
            },
        }))
        auth2 = json.loads(await ws.recv())
        if not auth2.get('data', {}).get('authenticated', False):
            print('❌ 認証失敗。VTube Studioでポップアップを許可してください。')
            return
        print('✅ 認証OK')

        # 2. パラメータ照合（新マッピング）
        our_params = {
            'EyeOpenLeft': (0, 1),
            'EyeOpenRight': (0, 1),
            'BrowLeftY': (0, 1),
            'BrowRightY': (0, 1),
            'MouthOpen': (0, 1),
            'MouthSmile': (0, 1),
            'FaceAngleX': (-30, 30),
            'FaceAngleZ': (-90, 90),
            'MocopiBodyAngleX': (-10, 10),
            'CheekPuff': (0, 1),
        }

        await ws.send(json.dumps({
            'apiName': 'VTubeStudioPublicAPI',
            'apiVersion': '1.0',
            'requestID': 'params',
            'messageType': 'InputParameterListRequest',
        }))
        params_resp = json.loads(await ws.recv())
        params = params_resp.get('data', {}).get('defaultParameters', [])
        model_names = {p['name'] for p in params}

        print(f'\nモデルパラメータ: {len(params)}件')
        print('\nparam_map 照合:')
        all_ok = True
        for name in our_params:
            ok = name in model_names
            print(f'  {"✅" if ok else "❌"} {name}')
            if not ok:
                all_ok = False

        if not all_ok:
            print('\n⚠ 一部パラメータが見つかりません')
            return
        print('\n✅ 全パラメータ一致')

        # 3. 表情注入テスト
        print('\n' + '='*50)
        print('表情注入テスト')

        # テスト1: 笑顔
        print('\n[テスト1] 笑顔（3秒）')
        await ws.send(json.dumps({
            'apiName': 'VTubeStudioPublicAPI',
            'apiVersion': '1.0',
            'requestID': 'inject_smile',
            'messageType': 'InjectParameterDataRequest',
            'data': {
                'parameterValues': [
                    {'id': 'MouthSmile', 'value': 0.8},
                    {'id': 'EyeOpenLeft', 'value': 0.6},
                    {'id': 'EyeOpenRight', 'value': 0.6},
                ],
            },
        }))
        resp = json.loads(await ws.recv())
        ok = resp.get('messageType') == 'InjectParameterDataResponse'
        print(f'  注入: {"OK" if ok else "失敗 " + str(resp)}')
        await asyncio.sleep(3)

        # テスト2: 驚き
        print('[テスト2] 驚き（3秒）')
        await ws.send(json.dumps({
            'apiName': 'VTubeStudioPublicAPI',
            'apiVersion': '1.0',
            'requestID': 'inject_surprise',
            'messageType': 'InjectParameterDataRequest',
            'data': {
                'parameterValues': [
                    {'id': 'EyeOpenLeft', 'value': 1.0},
                    {'id': 'EyeOpenRight', 'value': 1.0},
                    {'id': 'BrowLeftY', 'value': 0.8},
                    {'id': 'BrowRightY', 'value': 0.8},
                    {'id': 'MouthOpen', 'value': 0.5},
                ],
            },
        }))
        resp = json.loads(await ws.recv())
        ok = resp.get('messageType') == 'InjectParameterDataResponse'
        print(f'  注入: {"OK" if ok else "失敗 " + str(resp)}')
        await asyncio.sleep(3)

        # テスト3: リセット（通常表情に戻す）
        print('[テスト3] リセット')
        await ws.send(json.dumps({
            'apiName': 'VTubeStudioPublicAPI',
            'apiVersion': '1.0',
            'requestID': 'inject_reset',
            'messageType': 'InjectParameterDataRequest',
            'data': {
                'parameterValues': [
                    {'id': 'MouthSmile', 'value': 0.0},
                    {'id': 'MouthOpen', 'value': 0.0},
                    {'id': 'EyeOpenLeft', 'value': 1.0},
                    {'id': 'EyeOpenRight', 'value': 1.0},
                    {'id': 'BrowLeftY', 'value': 0.5},
                    {'id': 'BrowRightY', 'value': 0.5},
                ],
            },
        }))
        resp = json.loads(await ws.recv())
        print('  リセット完了')

        print('\n✅ 表情注入テスト完了')
        print('VTube Studioで表情変化が見えましたか？')

asyncio.run(check_vtube())
