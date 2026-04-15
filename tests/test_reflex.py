from brain.reflex_layer import apply_reflex, merge_spike_to_state

def test_reflex_basic():
    # 驚きワードのテスト
    spike = apply_reflex('え！まじで！')
    assert spike.surprise > 0, '驚きが検出されていない'
    print(f'驚きスパイク: surprise={spike.surprise}')

    # 呼びかけのテスト
    spike2 = apply_reflex('ねえ、聞いて')
    assert spike2.attention > 0, '呼びかけが検出されていない'
    print(f'呼びかけスパイク: attention={spike2.attention}')

    # 沈黙ペナルティのテスト
    spike3 = apply_reflex('', silence_minutes=60)
    assert spike3.loneliness > 0, '沈黙の孤独感が検出されていない'
    print(f'沈黙スパイク(60分): loneliness={spike3.loneliness}')

    # スパイクを状態に統合
    state = {'joy': 50, 'surprise': 0}
    state = merge_spike_to_state(state, spike)
    print(f'統合後の状態: {state}')

    print('反射層テスト: 全て成功')

test_reflex_basic()