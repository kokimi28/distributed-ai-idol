# tests/integration/test_6_pipeline.py
"""テスト6: パイプライン統合テスト（モックLLM + 実AivisSpeech）"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from broadcast.pipeline import BroadcastPipeline, PipelineConfig

speak_log = []


async def mock_llm(**kwargs):
    topic = kwargs.get('topic', '')
    phase = kwargs.get('phase', '')
    texts = {
        'opening': 'はーい、こんばんは。今日もやっていきます。',
        'INTRO': '%sの話なんだけどさ。' % topic,
        'DEVELOP': 'なんかね、%sって結構奥が深いんだよね……かな。' % topic,
        'DEEPEN': 'わたし、こういうの昔から好きだったかも。',
        'DECAY': 'まあ、そんな感じ。',
        'TRANSIT': 'あ、そういえば全然違う話なんだけど。',
        'comment_reaction': 'あ、コメントありがとう。',
    }
    return texts.get(phase, '%sについて話すね。' % topic)


def on_speak(action, result):
    engine = result.engine if result else 'N/A'
    text_preview = action.text[:30]
    speak_log.append('[%s/%s] %s... (engine=%s)' % (action.source, action.phase, text_preview, engine))


async def main():
    config = PipelineConfig(
        planned_duration_minutes=0.5,    # 30秒のテスト配信
        prefer_voice_engine='aivispeech',
        min_speak_interval=3.0,          # 3秒間隔
        max_silence=5.0,                 # 5秒で発話
        mode='broadcast',
        enable_vtube=False,              # VTubeなしでまずテスト
        initial_topics=[
            {'topic': '深夜のコンビニ', 'keywords': ['コンビニ', '深夜'], 'priority': 50},
            {'topic': '最近見た映画', 'keywords': ['映画'], 'priority': 40},
        ],
    )

    pipeline = BroadcastPipeline(config, mock_llm)
    pipeline.on_speak_callback = on_speak

    print('=== パイプライン統合テスト ===')
    print('（30秒間の自動配信テスト。OBSの音声ミキサーを確認してください）')
    print()

    result = await pipeline.start()
    print('起動: engine=%s' % result.get('voice_engine', 'N/A'))
    print()

    # 10秒後にコメント投入
    await asyncio.sleep(10)
    print('--- コメント投入: こんばんは！ ---')
    await pipeline.on_comment('こんばんは！', user_id='test_user')

    # さらに5秒後にスパチャ
    await asyncio.sleep(5)
    print('--- スパチャ投入: 応援してます！ ---')
    await pipeline.on_comment('応援してます！', user_id='fan', is_superchat=True)

    # 残りを待つ
    await asyncio.sleep(15)

    stop = await pipeline.stop()
    print()
    print('=== 結果 ===')
    print('総発話回数: %d' % stop['total_speaks'])
    print()
    print('--- 発話ログ ---')
    for log in speak_log:
        print('  %s' % log)
    print()

    if stop['total_speaks'] > 0:
        print('パイプライン統合テスト: 成功')
    else:
        print('パイプライン統合テスト: 発話なし')
        print('  → AivisSpeechが起動しているか確認')


if __name__ == '__main__':
    asyncio.run(main())
