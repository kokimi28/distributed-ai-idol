from memory.emotion_carry import calc_emotion_residue, apply_residue_to_initial_state
from datetime import datetime, timedelta

def test_emotion_carry():
    prev_emotions = {'joy': 80, 'sadness': 20, 'anger': 60}
    session_end = datetime.now() - timedelta(minutes=30)

    residue = calc_emotion_residue(prev_emotions, session_end)
    print(f'30分後の残り香: {residue}')

    assert residue['joy'] > 30, 'joyの残り香が少なすぎる'
    assert residue['anger'] < 15, 'angerが消えていない'

    initial = {'joy': 40, 'sadness': 0}
    merged = apply_residue_to_initial_state(initial, residue)
    print(f'残り香適用後の初期状態: {merged}')

    assert merged['joy'] > 40, '残り香が適用されていない'
    print('感情残り香テスト: 成功')

test_emotion_carry()