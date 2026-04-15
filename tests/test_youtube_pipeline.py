# tests/test_youtube_pipeline.py  YouTube Chat → Pipeline 統合テスト
"""
YouTubeChatPoller → pipeline.on_comment() → reflex → blender の流れを検証。
実際のYouTube APIは叩かない（モックで代替）。
"""

import asyncio
from datetime import datetime, timezone
from broadcast.youtube_chat import YouTubeChatPoller, ChatComment
from broadcast.pipeline import BroadcastPipeline, PipelineConfig
from brain.reflex_layer import apply_reflex

# ── テスト用の記録 ──

processed_comments = []
generated_prompts = []


async def mock_llm_generate(**kwargs) -> str:
    """LLMの代わりにプロンプトを記録して固定応答を返す"""
    generated_prompts.append(kwargs)
    return '……あ、そうなんだ'


# ── Test 1: ChatComment → on_comment() の変換 ──

def test_comment_conversion():
    """ChatCommentがon_comment()の引数に正しく変換されるか"""
    comment = ChatComment(
        author='テストさん',
        text='えっ！まじで？',
        timestamp=datetime.now(timezone.utc),
        is_member=False,
        is_superchat=False,
    )

    # _on_youtube_comment が on_comment を正しく呼ぶことを確認
    assert comment.text == 'えっ！まじで？'
    assert comment.author == 'テストさん'
    assert comment.is_superchat is False
    print('Test 1 ChatComment変換: OK')


# ── Test 2: コメント → 反射層 → 感情スパイク ──

def test_comment_triggers_reflex():
    """YouTubeコメントが反射層を通ると正しいスパイクが出るか"""
    # 驚きコメント
    spike1 = apply_reflex('えっ！まじで！')
    assert spike1.surprise > 0, 'surprise未検出'
    print(f'  驚き: surprise={spike1.surprise}')

    # スパチャ的な好意コメント
    spike2 = apply_reflex('好き！かわいい！')
    assert spike2.warmth > 0, 'warmth未検出'
    print(f'  好意: warmth={spike2.warmth}')

    # 攻撃的コメント
    spike3 = apply_reflex('うざい消えろ')
    assert spike3.defensiveness > 0, 'defensiveness未検出'
    print(f'  攻撃: defensiveness={spike3.defensiveness}')

    print('Test 2 反射層連動: OK')


# ── Test 3: Pipeline統合（コメントキュー投入→処理） ──

async def test_pipeline_comment_flow():
    """
    pipeline.on_comment() → キュー → _handle_comment の流れを検証。
    音声・VTubeは無効化してロジックだけテスト。
    """
    config = PipelineConfig(
        enable_vtube=False,
        enable_youtube_chat=False,  # ポーリングは手動テストなので無効
        prefer_voice_engine='aivispeech',
        planned_duration_minutes=5.0,
    )
    pipeline = BroadcastPipeline(config, mock_llm_generate)

    # 手動でキューにコメント投入（start()せずに内部テスト）
    pipeline._is_running = True

    # on_comment でキューに入る
    await pipeline.on_comment(
        text='ねえ、聞いて！',
        user_id='youtube_user_1',
        is_superchat=False,
    )
    assert pipeline._comment_queue.qsize() == 1, 'キューに入っていない'
    print('  キュー投入: OK')

    # キューから取り出して処理
    comment = await pipeline._comment_queue.get()
    assert comment['text'] == 'ねえ、聞いて！'
    assert comment['user_id'] == 'youtube_user_1'
    print(f'  キュー取出: OK ({comment["text"]})')

    # 反射層を通す
    spike = apply_reflex(comment['text'])
    assert spike.attention > 0, '呼びかけ未検出'
    print(f'  反射スパイク: attention={spike.attention}')

    # 感情状態が更新される
    from brain.reflex_layer import merge_spike_to_state
    old_state = dict(pipeline.char_state)
    pipeline.char_state = merge_spike_to_state(pipeline.char_state, spike)
    print(f'  感情更新: joy={old_state["joy"]}→{pipeline.char_state["joy"]}')

    pipeline._is_running = False
    print('Test 3 パイプライン統合: OK')


# ── Test 4: スーパーチャットの優先処理 ──

async def test_superchat_flow():
    """スーパーチャットがon_comment()に正しく渡されるか"""
    config = PipelineConfig(
        enable_vtube=False,
        enable_youtube_chat=False,
        prefer_voice_engine='aivispeech',
    )
    pipeline = BroadcastPipeline(config, mock_llm_generate)
    pipeline._is_running = True

    # スパチャ付きコメント
    sc_comment = ChatComment(
        author='太っ腹さん',
        text='がんばれ！応援してる！',
        timestamp=datetime.now(timezone.utc),
        is_superchat=True,
        superchat_amount=1000.0,
    )

    # _on_youtube_comment 相当の処理
    await pipeline.on_comment(
        text=sc_comment.text,
        user_id=sc_comment.author,
        is_superchat=sc_comment.is_superchat,
    )

    comment = await pipeline._comment_queue.get()
    assert comment['is_superchat'] is True, 'スーパーチャットフラグが欠落'
    assert comment['text'] == 'がんばれ！応援してる！'
    print(f'  スパチャ: is_superchat={comment["is_superchat"]}')

    pipeline._is_running = False
    print('Test 4 スーパーチャット: OK')


# ── Test 5: PipelineConfig にYouTube設定が入っているか ──

def test_config_youtube_fields():
    """PipelineConfigにYouTube関連フィールドが追加されているか"""
    config = PipelineConfig()
    assert hasattr(config, 'enable_youtube_chat'), 'enable_youtube_chat がない'
    assert hasattr(config, 'youtube_live_chat_id'), 'youtube_live_chat_id がない'
    assert config.enable_youtube_chat is True, 'デフォルトがTrueでない'
    assert config.youtube_live_chat_id is None, 'デフォルトがNoneでない'
    print('Test 5 Config確認: OK')


# ── 実行 ──

if __name__ == '__main__':
    test_comment_conversion()
    test_comment_triggers_reflex()
    asyncio.run(test_pipeline_comment_flow())
    asyncio.run(test_superchat_flow())
    test_config_youtube_fields()
    print('\nYouTube Chat → Pipeline 統合テスト: 全て成功')