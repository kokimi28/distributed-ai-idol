# tests/integration/test_5_vtube.py
"""テスト5: VTube Studio 表情制御テスト"""
import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


async def test_5a_websocket():
    """5-1: WebSocket接続テスト"""
    print('=== 5-1: VTube Studio WebSocket接続 ===')
    try:
        import websockets
    except ImportError:
        print('websockets がインストールされていません')
        print('  → pip install websockets')
        return False

    try:
        ws = await websockets.connect('ws://localhost:8001')
        print('WebSocket接続: OK')

        await ws.send(json.dumps({
            'apiName': 'VTubeStudioPublicAPI',
            'apiVersion': '1.0',
            'requestID': 'test1',
            'messageType': 'APIStateRequest',
            'data': {},
        }))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        active = resp.get('data', {}).get('active', False)
        name = resp.get('data', {}).get('currentModelName', '不明')
        print('API状態: %s' % ('アクティブ' if active else '非アクティブ'))
        print('現在のモデル: %s' % name)
        await ws.close()
        return True

    except ConnectionRefusedError:
        print('VTube Studioに接続できません')
        print('  → VTube Studioが起動しているか確認')
        print('  → APIが有効か確認（ポート8001）')
        return False
    except Exception as e:
        print('エラー: %s' % e)
        return False


async def test_5b_expression():
    """5-2: 表情制御テスト"""
    print()
    print('=== 5-2: 表情制御テスト ===')
    from broadcast.vtube_control import VTubeController, emotion_to_expression

    ctrl = VTubeController(host='localhost', port=8001)
    connected = await ctrl.connect()
    if connected:
        print('VTube Studio認証: OK')
    else:
        print('VTube Studio認証: NG')
        print('  → VTube Studioで認証ダイアログが出たら「許可」を押してください')
        print('  → もう一度このスクリプトを実行してください')
        return

    print()
    emotions_test = [
        ('喜び', {'joy': 80}, 'broadcast'),
        ('驚き', {'surprise': 90}, 'broadcast'),
        ('悲しみ', {'sadness': 70}, 'private'),
        ('照れ', {'embarrass': 60}, 'private'),
    ]

    for name, emo, mode in emotions_test:
        print('--- %s表情テスト（3秒間）---' % name)
        expr = emotion_to_expression(emo, mode)
        await ctrl.apply_expression(expr)
        await asyncio.sleep(3)

    print('--- ニュートラルに戻す ---')
    neutral = emotion_to_expression({}, 'broadcast')
    await ctrl.apply_expression(neutral)

    await ctrl.disconnect()
    print()
    print('表情制御テスト: 完了')
    print()
    print('※ VTube Studioのモデルの表情が変化したか目視で確認してください')
    print('※ モデルによってはパラメータ名が異なり反応しない場合があります')
    print('  → vtube_control.py の param_map を実際のモデルに合わせて調整')


async def main():
    ok = await test_5a_websocket()
    if ok:
        await test_5b_expression()


if __name__ == '__main__':
    asyncio.run(main())
