# tests/test_autonomous_talk.py
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.stream_clock import StreamClock
from brain.topic_engine import TopicEngine
from brain.autonomous_talk import AutonomousTalk, TalkAction
from brain.comment_blender import judge, BlendMode
from brain.reflex_layer import EmotionSpike, apply_reflex


async def mock_generate(**kwargs):
    """LLMの代わりにモック生成"""
    hint = kwargs.get('prompt_hint', '')
    topic = kwargs.get('topic', '')
    phase = kwargs.get('phase', '')
    return f'[{phase}] {topic}についての発話（モック）'


async def test_autonomous_loop():
    """自律発話ループの基本動作テスト"""
    clock = StreamClock(planned_duration_minutes=1.0)  # 1分の短い配信
    engine = TopicEngine()
    talk = AutonomousTalk(
        clock=clock,
        topic_engine=engine,
        generate_fn=mock_generate,
        min_interval=0.1,   # テスト用に短く
        max_interval=0.5,
    )

    # 話題を投入
    talk.prepare_topics([
        {'topic': '深夜のコンビニ', 'keywords': ['コンビニ', '深夜'], 'priority': 50},
        {'topic': 'お気に入りの音楽', 'keywords': ['音楽', '曲'], 'priority': 40},
    ])

    clock.start()

    # 最初の3発話を取得
    actions = []
    count = 0
    async for action in talk.run():
        actions.append(action)
        count += 1
        if count >= 3:
            clock.stop()
            break

    assert len(actions) == 3
    print(f'✓ 自律発話 {len(actions)} 回生成')
    for i, a in enumerate(actions):
        print(f'  [{i+1}] source={a.source}, phase={a.phase}, topic={a.topic[:15]}...')


async def test_interrupt_injection():
    """割込み注入テスト"""
    clock = StreamClock(planned_duration_minutes=1.0)
    engine = TopicEngine()
    talk = AutonomousTalk(
        clock=clock, topic_engine=engine,
        generate_fn=mock_generate,
        min_interval=0.1, max_interval=0.3,
    )
    talk.prepare_topics([
        {'topic': 'テスト話題', 'keywords': [], 'priority': 50},
    ])

    clock.start()

    actions = []
    count = 0
    async for action in talk.run():
        actions.append(action)
        count += 1
        # 2発話目の後に割込みを注入
        if count == 2:
            interrupt = TalkAction(
                text='あ、コメント来てる！',
                topic='コメント反応',
                phase='interrupt',
                heat=80,
                source='comment_reaction',
            )
            talk.inject_interrupt(interrupt)
        if count >= 4:
            clock.stop()
            break

    # 割込みが含まれているか
    sources = [a.source for a in actions]
    assert 'comment_reaction' in sources, f'割込みが注入されていない: {sources}'
    print(f'✓ 割込み注入成功: sources={sources}')


def test_comment_blender():
    """コメント割込み判定テスト"""
    print('\n=== comment_blender テスト ===')

    # スパチャ → IMMEDIATE
    spike = EmotionSpike(warmth=30)
    d = judge('応援してます！', spike, is_superchat=True)
    assert d.mode == BlendMode.IMMEDIATE
    print(f'✓ スパチャ → {d.mode.value} (reason={d.reason})')

    # 攻撃的コメント → IMMEDIATE
    spike2 = apply_reflex('うざい消えろ')
    d2 = judge('うざい消えろ', spike2)
    assert d2.mode == BlendMode.IMMEDIATE
    print(f'✓ 攻撃 → {d2.mode.value} (reason={d2.reason})')

    # 名指し → IMMEDIATE
    spike3 = EmotionSpike(attention=40)
    d3 = judge('○○ちゃん、今日かわいい！', spike3, is_mention=True)
    assert d3.mode == BlendMode.IMMEDIATE
    print(f'✓ 名指し → {d3.mode.value} (reason={d3.reason})')

    # 関連コメント → WEAVE_IN or AT_BREAK
    spike4 = EmotionSpike(warmth=25)
    d4 = judge('コンビニの新作気になる', spike4,
               comment_keywords=['コンビニ', '新作'],
               topic_keywords=['コンビニ', '深夜'])
    assert d4.mode in (BlendMode.WEAVE_IN, BlendMode.AT_BREAK)
    print(f'✓ 関連コメント → {d4.mode.value} (reason={d4.reason})')

    # 無関連・低スパイク → QUEUE
    spike5 = EmotionSpike()
    d5 = judge('明日の天気どうかな', spike5,
               comment_keywords=['天気', '明日'],
               topic_keywords=['コンビニ', '深夜'])
    assert d5.mode == BlendMode.QUEUE
    print(f'✓ 無関連 → {d5.mode.value} (reason={d5.reason})')

    # スパム → IGNORE
    spike6 = EmotionSpike()
    d6 = judge('あ', spike6, recent_comments=['あ', 'あ', 'あ', 'あ', 'あ'])
    assert d6.mode == BlendMode.IGNORE
    print(f'✓ スパム → {d6.mode.value} (reason={d6.reason})')

    print('\ncomment_blender テスト: 全て成功')


async def main():
    await test_autonomous_loop()
    await test_interrupt_injection()
    test_comment_blender()
    print('\n=== 自律発話エンジン テスト: 全て成功 ===')


asyncio.run(main())
