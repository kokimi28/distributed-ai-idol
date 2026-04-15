# tests/integration/test_8_claude_api.py
"""テスト8: Claude API接続テスト

話題生成 + 実Claude APIによる発話生成をテストする。
AivisSpeechが起動していれば音声も出る。
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from dotenv import load_dotenv
load_dotenv()

from brain.topic_generator import generate_topics
from llm.claude_bridge import ClaudeBridge
from broadcast.pipeline import BroadcastPipeline, PipelineConfig


def test_api_key():
    """APIキーが設定されているか確認"""
    key = os.getenv('ANTHROPIC_API_KEY', '')
    if not key or key.startswith('sk-ant-xxxx'):
        print('ANTHROPIC_API_KEY が未設定またはダミー値です')
        print('  → .env ファイルを確認してください')
        return False
    print('APIキー: 設定済み (%s...%s)' % (key[:10], key[-4:]))
    return True


def test_topic_generation():
    """話題リスト自動生成テスト"""
    print()
    print('=== 話題リスト生成 ===')
    topics = generate_topics(
        theme='雑談',
        count=5,
        time_of_day=None,  # 自動判定
    )

    if not topics:
        print('話題生成: 失敗')
        return None

    print('生成された話題:')
    for i, t in enumerate(topics):
        print('  %d. %s (priority=%d, keywords=%s)' % (
            i + 1, t['topic'], t['priority'], t['keywords'][:3]
        ))
    print()
    return topics


async def test_claude_bridge():
    """ClaudeBridgeの単発テスト"""
    print('=== Claude Bridge テスト ===')
    bridge = ClaudeBridge(mode='broadcast')

    # 感情状態をセット
    emotions = {'joy': 40, 'tension': 30, 'affection': 50}
    bridge.set_char_state_ref(emotions)

    # INTRO フェーズ
    text = await bridge.generate(
        prompt_hint='話題「深夜のコンビニ」を自然に切り出す。軽い入りで1文。',
        topic='深夜のコンビニ',
        phase='INTRO',
        heat=50,
    )
    print('INTRO: %s' % text)

    # DEVELOP フェーズ
    text2 = await bridge.generate(
        prompt_hint='話題「深夜のコンビニ」を展開する。具体的なエピソード。',
        topic='深夜のコンビニ',
        phase='DEVELOP',
        heat=65,
    )
    print('DEVELOP: %s' % text2)

    # コメント反応
    text3 = await bridge.generate(
        prompt_hint='コメント「わかるー！」への反応。weave_inモード。',
        topic='コメント反応',
        phase='comment_reaction',
        heat=70,
    )
    print('COMMENT: %s' % text3)

    print()
    return True


async def test_pipeline_with_claude(topics):
    """実Claude API + AivisSpeech のパイプラインテスト"""
    print('=== パイプライン統合テスト（実Claude API）===')
    print('30秒間のテスト配信。')
    print()

    bridge = ClaudeBridge(mode='broadcast')

    config = PipelineConfig(
        planned_duration_minutes=0.5,    # 30秒
        prefer_voice_engine='aivispeech',
        min_speak_interval=5.0,
        max_silence=8.0,
        mode='broadcast',
        enable_vtube=False,  # VTubeなしで（API接続テストに集中）
        initial_topics=topics[:5] if topics else [
            {'topic': '最近のこと', 'keywords': ['日常'], 'priority': 50},
        ],
    )

    pipeline = BroadcastPipeline(config, bridge.generate)
    bridge.set_char_state_ref(pipeline.char_state)

    speak_log = []

    def on_speak(action, result):
        engine = result.engine if result else 'N/A'
        speak_log.append('[%s] %s' % (action.phase, action.text[:40]))

    pipeline.on_speak_callback = on_speak

    result = await pipeline.start()
    print('起動: engine=%s' % result.get('voice_engine', 'N/A'))

    # 15秒後にコメント
    await asyncio.sleep(15)
    print('[15秒] コメント投入: 最近寒くない？')
    await pipeline.on_comment('最近寒くない？', user_id='test')

    # 残りを待つ
    await asyncio.sleep(15)

    stop = await pipeline.stop()
    print()
    print('=== 結果 ===')
    print('総発話: %d回' % stop['total_speaks'])
    for log in speak_log:
        print('  %s' % log)
    print()

    if stop['total_speaks'] > 0:
        print('Claude API パイプラインテスト: 成功')
    else:
        print('Claude API パイプラインテスト: 発話なし')


async def main():
    # 1. APIキー確認
    if not test_api_key():
        return

    # 2. 話題生成
    topics = test_topic_generation()

    # 3. Claude Bridge単発テスト
    ok = await test_claude_bridge()
    if not ok:
        return

    # 4. パイプライン統合（実Claude + AivisSpeech）
    await test_pipeline_with_claude(topics)


if __name__ == '__main__':
    asyncio.run(main())
