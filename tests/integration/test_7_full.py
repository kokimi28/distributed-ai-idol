# tests/integration/test_7_full.py
"""テスト7: フル統合テスト（AivisSpeech + VTube Studio + Pipeline）"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from broadcast.pipeline import BroadcastPipeline, PipelineConfig


async def mock_llm(**kwargs):
    topic = kwargs.get('topic', '')
    phase = kwargs.get('phase', '')
    texts = {
        'opening': 'こんばんは。今日もやっていくよ。',
        'INTRO': 'ねえ、%sの話してもいい？' % topic,
        'DEVELOP': 'なんかさ、%sってちょっと不思議だよね……かな。' % topic,
        'DEEPEN': '昔からこういうの気になってて……あ、でも違うかな。',
        'DECAY': 'うん、まあ、そんな感じ。',
        'TRANSIT': 'あ、そういえばさ。',
        'comment_reaction': 'えっ、まじで？ ありがとう。',
    }
    return texts.get(phase, 'えっとね、%sの話。' % topic)


async def main():
    config = PipelineConfig(
        planned_duration_minutes=1.0,    # 1分のテスト配信
        prefer_voice_engine='aivispeech',
        min_speak_interval=5.0,
        max_silence=8.0,
        mode='broadcast',
        enable_vtube=True,               # VTube Studio ON
        vtube_host='localhost',
        vtube_port=8001,
        initial_topics=[
            {'topic': '雨の日', 'keywords': ['雨', '傘', '天気'], 'priority': 50},
            {'topic': '好きな食べ物', 'keywords': ['食べ物', '料理'], 'priority': 40},
            {'topic': '最近のマイブーム', 'keywords': ['趣味'], 'priority': 30},
        ],
    )

    pipeline = BroadcastPipeline(config, mock_llm)

    print('=== フル統合テスト（1分間）===')
    print()
    print('確認ポイント:')
    print('  1. AivisSpeechで音声が出る（OBSの音声ミキサーで確認）')
    print('  2. VTube Studioのモデルの表情が変化する')
    print('  3. コメントに反応する')
    print('  4. 話題が自然に遷移する')
    print()

    result = await pipeline.start()
    vtube_ok = result.get('vtube_connected', False)
    voice_engine = result.get('voice_engine', 'N/A')
    print('起動: voice=%s, vtube=%s' % (voice_engine, 'OK' if vtube_ok else '未接続'))
    print('--- 1分間のテスト配信を開始 ---')
    print()

    # 20秒後にコメント
    await asyncio.sleep(20)
    print('[20秒] コメント: こんばんは！')
    await pipeline.on_comment('こんばんは！', user_id='user1')

    # 40秒後にもう1つ
    await asyncio.sleep(20)
    print('[40秒] コメント: 雨の日いいよね')
    await pipeline.on_comment('雨の日いいよね', user_id='user2')

    # 残り待ち
    await asyncio.sleep(20)

    stop = await pipeline.stop()
    total = stop['total_speaks']
    print()
    print('=== テスト完了 ===')
    print('総発話: %d回' % total)
    print()

    if total >= 5 and vtube_ok:
        print('フル統合テスト: 成功（音声+表情+コメント反応）')
    elif total >= 5:
        print('フル統合テスト: 音声OK / VTube未接続')
        print('  → VTube StudioのAPI有効化を確認')
    elif total > 0:
        print('フル統合テスト: 発話少なめ（%d回）。間隔設定を確認' % total)
    else:
        print('フル統合テスト: 発話なし')
        print('  → AivisSpeechが起動しているか確認')


if __name__ == '__main__':
    asyncio.run(main())
