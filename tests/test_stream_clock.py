# tests/test_stream_clock.py
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.stream_clock import StreamClock, StreamPhase


def test_stream_clock():
    clock = StreamClock(planned_duration_minutes=60.0)

    # 起動前は ENDED
    assert clock.phase == StreamPhase.ENDED
    print('✓ 起動前: ENDED')

    # 配信開始
    clock.start()
    assert clock.is_live
    assert clock.phase == StreamPhase.OPENING
    print(f'✓ 配信開始: phase={clock.phase.value}')

    # tick で状態取得
    state = clock.tick()
    assert state['phase'] == 'opening'
    assert state['fatigue'] >= 0
    print(f'✓ tick: {state}')

    # 発話記録
    clock.on_speak()
    assert clock.silence_seconds < 1.0
    print(f'✓ on_speak: silence={clock.silence_seconds:.1f}s')

    # コメント受信（疲労回復）
    old_fatigue = clock.fatigue
    clock.on_comment()
    assert clock.fatigue <= old_fatigue
    print(f'✓ on_comment: fatigue {old_fatigue:.1f} → {clock.fatigue:.1f}')

    # should_speak（沈黙検知）
    assert not clock.should_speak(silence_threshold=10.0)
    print('✓ should_speak=False（直後は沈黙なし）')

    # 配信終了
    clock.stop()
    assert not clock.is_live
    assert clock.phase == StreamPhase.ENDED
    print('✓ 配信終了: ENDED')

    print('\nstream_clock テスト: 全て成功')


test_stream_clock()
