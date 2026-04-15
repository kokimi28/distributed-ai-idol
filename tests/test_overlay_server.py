# tests/test_overlay_server.py
"""
OverlayServer単体テスト

1. サーバー起動・停止
2. シミュレートイベント送信（ブラウザで debug_viewer.html を開いて確認）

Usage:
  python -m tests.test_overlay_server

  別のブラウザで overlay/debug_viewer.html を開くと
  感情バー・話題・コメントイベントがリアルタイム表示される
"""
import asyncio
import time
import random
from broadcast.overlay_server import OverlayServer


async def test_basic():
    """起動・停止テスト"""
    print('=== OverlayServer 基本テスト ===')
    server = OverlayServer(port=8765)
    ok = await server.start()
    assert ok, 'サーバー起動失敗'
    print(f'[OK] サーバー起動: ws://127.0.0.1:8765')
    assert server.is_running
    assert server.client_count == 0
    print(f'[OK] クライアント数: {server.client_count}')

    await server.stop()
    assert not server.is_running
    print('[OK] サーバー停止')
    print()


async def test_simulation():
    """シミュレートイベント送信（ブラウザ確認用）"""
    print('=== OverlayServer シミュレーション ===')
    print('ブラウザで overlay/debug_viewer.html を開いてください')
    print('15秒間シミュレートイベントを送信します')
    print()

    server = OverlayServer(port=8765)
    await server.start()

    # 感情の初期状態
    emotions = {
        'joy': 40, 'sadness': 0, 'anger': 0, 'surprise': 0,
        'embarrass': 0, 'fear': 0, 'affection': 50,
        'fatigue': 0, 'tension': 40, 'loneliness': 0,
    }
    topics = [
        ('AIと人間の違い', ['意識', '感情'], 50),
        ('宇宙の話', ['星', '銀河'], 60),
        ('猫の動画', ['猫', 'かわいい'], 70),
    ]
    topic_idx = 0
    phase_list = ['INTRO', 'DEVELOP', 'DEVELOP', 'DEVELOP', 'DECAY', 'TRANSIT']
    phase_idx = 0
    elapsed = 0.0

    # シナリオ: 感情が大きく変動するパターン
    scenarios = [
        # (joy, sadness, tension, loneliness, affection, fatigue, surprise) の目標値
        {'joy':70,'tension':20,'loneliness':5,'affection':60,'fatigue':5,'surprise':0},   # 楽しい序盤
        {'joy':80,'tension':15,'loneliness':0,'affection':70,'fatigue':10,'surprise':0},
        {'joy':40,'tension':60,'loneliness':10,'affection':50,'fatigue':15,'surprise':40}, # 驚きイベント
        {'joy':30,'tension':70,'loneliness':20,'affection':40,'fatigue':20,'surprise':10},
        {'joy':20,'tension':30,'loneliness':50,'affection':30,'fatigue':30,'surprise':0},  # 静かに
        {'joy':15,'tension':20,'loneliness':60,'affection':25,'fatigue':40,'surprise':0},  # 寂しい
        {'joy':60,'tension':30,'loneliness':10,'affection':80,'fatigue':35,'surprise':0},  # コメントで復活
        {'joy':80,'tension':20,'loneliness':5,'affection':85,'fatigue':40,'surprise':20},
        {'joy':50,'tension':15,'loneliness':15,'affection':60,'fatigue':55,'surprise':0},  # 疲れてきた
        {'joy':30,'tension':10,'loneliness':30,'affection':50,'fatigue':70,'surprise':0},  # だるい
    ]

    for i in range(30):
        # シナリオの目標値に向かって感情を変動
        target = scenarios[min(i//3, len(scenarios)-1)]
        for k in target:
            if k in emotions:
                emotions[k] = emotions[k] + int((target[k] - emotions[k]) * 0.4) + random.randint(-3, 3)
                emotions[k] = max(0, min(100, emotions[k]))
        elapsed += 0.5

        # フェーズ進行
        topic_name, kw, heat = topics[topic_idx % len(topics)]
        phase = phase_list[phase_idx % len(phase_list)]
        heat = max(0, heat + random.randint(-5, 3))

        # 状態配信
        server.broadcast_state(
            char_state=dict(emotions),
            topic_info={'topic': topic_name, 'phase': phase, 'heat': heat},
            clock_info={'elapsed_min': elapsed, 'fatigue': emotions['fatigue'], 'comment_silence_sec': i * 2},
        )

        # たまにコメントイベント（種別を多様に）
        if i % 4 == 2:
            spike = ['warmth','surprise','attention','joy_reflex','fear_reflex','warmth','surprise'][i % 7]
            texts = {
                'warmth': 'かわいい！好き！',
                'surprise': 'えっまじ？！',
                'attention': 'ねえねえ聞いて',
                'joy_reflex': '久しぶりー！会いたかった',
                'fear_reflex': 'やばい怖い',
            }
            server.broadcast_comment(
                text=texts.get(spike, 'こんばんはー'),
                user_id=f'user_{random.randint(1,99)}',
                spike_type=spike,
                spike_amount=30+random.randint(0, 30),
            )
            print(f'  [{elapsed:.0f}m] comment: {spike} +{30+random.randint(0,30)}')

        # フェーズ変化
        old_phase = phase
        phase_idx += 1
        new_phase = phase_list[phase_idx % len(phase_list)]
        if old_phase != new_phase:
            server.broadcast_phase_change(phase=new_phase, topic=topic_name, heat=heat)

        # 話題切り替え（TRANSITの次）
        if new_phase == 'INTRO' and old_phase == 'TRANSIT':
            topic_idx += 1
            new_topic, new_kw, _ = topics[topic_idx % len(topics)]
            server.broadcast_topic_change(topic=new_topic, keywords=new_kw)
            print(f'  [{elapsed:.0f}m] topic change -> {new_topic}')

        clients = server.client_count
        if i % 5 == 0:
            print(f'  [{elapsed:.0f}m] state sent | joy={emotions["joy"]} tension={emotions["tension"]} | clients={clients}')

        await asyncio.sleep(0.5)

    print()
    print(f'[OK] 30イベント送信完了 (最終クライアント数: {server.client_count})')
    await server.stop()
    print('[OK] サーバー停止')


if __name__ == '__main__':
    asyncio.run(test_basic())
    print()
    asyncio.run(test_simulation())
