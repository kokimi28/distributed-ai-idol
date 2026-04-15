# tests/test_pipeline.py
"""
voice/synthesizer, broadcast/vtube_control, broadcast/pipeline の統合テスト。
外部サービス（AivisSpeech, VTube Studio）なしで動作するモックテスト。
"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice.synthesizer import VoiceSettings, SynthResult, VoicePipeline
from broadcast.vtube_control import emotion_to_expression, FaceExpression
from broadcast.pipeline import BroadcastPipeline, PipelineConfig


# ── emotion_to_expression テスト ────────────────────────

def test_emotion_to_expression():
    print('=== emotion_to_expression テスト ===')

    # joy=80 → 笑顔
    expr = emotion_to_expression({'joy': 80}, 'broadcast')
    assert expr.eye_smile_left > 0.3, f'joy高→eye_smile: {expr.eye_smile_left}'
    assert expr.mouth_smile > 0.2, f'joy高→mouth_smile: {expr.mouth_smile}'
    print(f'✓ joy=80(配信): smile={expr.mouth_smile:.2f}, eye_smile={expr.eye_smile_left:.2f}')

    # sadness=70 → 下がった眉・目が細く
    expr2 = emotion_to_expression({'sadness': 70}, 'private')
    assert expr2.brow_left_y < 0, f'sadness→brow下がる: {expr2.brow_left_y}'
    assert expr2.eye_open_left < 1.0, f'sadness→目が細く: {expr2.eye_open_left}'
    print(f'✓ sadness=70(個人): brow={expr2.brow_left_y:.2f}, eye={expr2.eye_open_left:.2f}')

    # surprise=90 → 目が大きく・眉が上がる
    expr3 = emotion_to_expression({'surprise': 90}, 'broadcast')
    assert expr3.eye_open_left > 0.2, f'surprise→目が大きく: {expr3.eye_open_left}'
    assert expr3.brow_left_y > 0.2, f'surprise→眉が上がる: {expr3.brow_left_y}'
    print(f'✓ surprise=90(配信): eye_open={expr3.eye_open_left:.2f}, brow={expr3.brow_left_y:.2f}')

    # embarrass → 頬の赤み
    expr4 = emotion_to_expression({'embarrass': 60}, 'private')
    assert expr4.cheek_blush > 0.3, f'embarrass→cheek_blush: {expr4.cheek_blush}'
    print(f'✓ embarrass=60(個人): blush={expr4.cheek_blush:.2f}')

    # soto vs uchi の抑制差
    expr_soto = emotion_to_expression({'joy': 80}, 'broadcast')
    expr_uchi = emotion_to_expression({'joy': 80}, 'private')
    assert expr_uchi.mouth_smile > expr_soto.mouth_smile, \
        f'uchi > soto: {expr_uchi.mouth_smile} vs {expr_soto.mouth_smile}'
    print(f'✓ soto/uchi抑制: broadcast={expr_soto.mouth_smile:.2f} < private={expr_uchi.mouth_smile:.2f}')

    # 複合感情
    expr5 = emotion_to_expression({'joy': 50, 'fatigue': 60}, 'broadcast')
    print(f'✓ 複合(joy+fatigue): smile={expr5.mouth_smile:.2f}, eye={expr5.eye_open_left:.2f}')

    print('emotion_to_expression テスト: 全て成功\n')


# ── VoiceSettings テスト ────────────────────────────────

def test_voice_settings():
    print('=== VoiceSettings テスト ===')

    s = VoiceSettings()
    assert 0 <= s.stability <= 1
    assert 0 <= s.similarity_boost <= 1
    print(f'✓ デフォルト値: stability={s.stability}, similarity={s.similarity_boost}')

    s2 = VoiceSettings(stability=0.3, similarity_boost=0.9, style=0.6)
    assert s2.stability == 0.3
    print(f'✓ カスタム値: stability={s2.stability}, style={s2.style}')

    print('VoiceSettings テスト: 成功\n')


# ── Pipeline統合テスト（モック）──────────────────────────

async def mock_llm_generate(**kwargs):
    """LLMのモック"""
    topic = kwargs.get('topic', '不明')
    phase = kwargs.get('phase', '?')
    return f'[{phase}] {topic}についてのモック発話'


async def test_pipeline_lifecycle():
    print('=== Pipeline ライフサイクルテスト ===')

    config = PipelineConfig(
        planned_duration_minutes=0.5,  # 30秒の短い配信
        prefer_voice_engine='aivispeech',
        min_speak_interval=0.1,
        max_silence=0.3,
        mode='broadcast',
        enable_vtube=False,  # VTube Studio未接続
        initial_topics=[
            {'topic': '深夜のコンビニ', 'keywords': ['コンビニ'], 'priority': 50},
            {'topic': '最近のアニメ', 'keywords': ['アニメ'], 'priority': 40},
        ],
    )

    pipeline = BroadcastPipeline(config, mock_llm_generate)

    # 開始
    start_result = await pipeline.start()
    assert start_result['status'] == 'started'
    assert start_result['topics_loaded'] == 2
    print(f'✓ パイプライン開始: topics={start_result["topics_loaded"]}')

    # ステータス確認
    status = pipeline.get_status()
    assert status['is_running']
    print(f'✓ ステータス: running={status["is_running"]}')

    # コメント投入
    await pipeline.on_comment('こんばんは！', user_id='user1')
    await asyncio.sleep(0.3)
    print('✓ コメント投入: こんばんは！')

    # スパチャ
    await pipeline.on_comment('応援してます！', user_id='user2', is_superchat=True)
    await asyncio.sleep(0.3)
    print('✓ スパチャ投入: 応援してます！')

    # 話題追加
    pipeline.add_topics([
        {'topic': '新しい話題', 'keywords': ['new'], 'priority': 60},
    ])
    print('✓ 話題追加')

    # 少し動かす
    await asyncio.sleep(1.0)

    # 停止
    stop_result = await pipeline.stop()
    assert stop_result['status'] == 'stopped'
    print(f'✓ パイプライン停止: speaks={stop_result["total_speaks"]}')
    print(f'  最終感情: {stop_result["final_emotions"]}')

    print('Pipeline ライフサイクルテスト: 成功\n')


async def test_pipeline_comment_handling():
    print('=== Pipeline コメント処理テスト ===')

    config = PipelineConfig(
        planned_duration_minutes=0.5,
        min_speak_interval=0.1,
        max_silence=0.3,
        enable_vtube=False,
        initial_topics=[
            {'topic': 'テスト話題', 'keywords': [], 'priority': 50},
        ],
    )

    pipeline = BroadcastPipeline(config, mock_llm_generate)
    await pipeline.start()

    # 攻撃的コメント → 感情状態が変化するはず
    initial_anger = pipeline.char_state.get('anger', 0)
    await pipeline.on_comment('うざい消えろ', user_id='troll')
    await asyncio.sleep(0.5)

    assert pipeline.char_state['anger'] > initial_anger, \
        f'攻撃→anger上昇: {initial_anger} → {pipeline.char_state["anger"]}'
    print(f'✓ 攻撃的コメント→anger: {initial_anger} → {pipeline.char_state["anger"]}')

    # 好意コメント → affection上昇
    initial_affection = pipeline.char_state.get('affection', 0)
    await pipeline.on_comment('好き！かわいい！', user_id='fan')
    await asyncio.sleep(0.5)

    assert pipeline.char_state['affection'] >= initial_affection, \
        f'好意→affection: {initial_affection} → {pipeline.char_state["affection"]}'
    print(f'✓ 好意コメント→affection: {initial_affection} → {pipeline.char_state["affection"]}')

    await pipeline.stop()
    print('Pipeline コメント処理テスト: 成功\n')


async def main():
    test_emotion_to_expression()
    test_voice_settings()
    await test_pipeline_lifecycle()
    await test_pipeline_comment_handling()
    print('🎉 全テスト通過')


asyncio.run(main())
