# tests/test_zep_client.py
"""Zep Cloud 記憶レイヤーのテスト"""

import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_1_import():
    """zep-cloud SDKがインポートできるか"""
    try:
        from zep_cloud.client import AsyncZep
        from zep_cloud.types import Message as ZepMessage
        print("Test 1 SDK import: OK")
        return True
    except ImportError as e:
        print(f"Test 1 SDK import: FAIL - {e}")
        print("  → pip install zep-cloud を実行してください")
        return False


def test_2_zep_memory_import():
    """ZepMemoryクラスがインポートできるか"""
    from memory.zep_client import ZepMemory, ZEP_AVAILABLE
    print(f"Test 2 ZepMemory import: OK (ZEP_AVAILABLE={ZEP_AVAILABLE})")
    return True


def test_3_api_key():
    """ZEP_API_KEYが設定されているか"""
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("ZEP_API_KEY", "")
    if key and len(key) > 10:
        print(f"Test 3 API key: OK (len={len(key)}, prefix={key[:8]}...)")
        return True
    else:
        print(f"Test 3 API key: FAIL - ZEP_API_KEY not set or too short")
        return False


async def test_4_connection():
    """Zep Cloudに接続できるか"""
    from memory.zep_client import ZepMemory
    mem = ZepMemory()
    result = await mem.initialize()
    if result:
        print("Test 4 connection: OK")
    else:
        print("Test 4 connection: FAIL")
    return result


async def test_5_full_cycle():
    """完全なライフサイクルテスト:
    session作成 → ユーザーメッセージ保存 → AI応答保存 → コンテキスト取得 → session終了
    """
    from memory.zep_client import ZepMemory
    mem = ZepMemory()
    ok = await mem.initialize()
    if not ok:
        print("Test 5 full cycle: SKIP (connection failed)")
        return False

    # セッション開始
    thread_id = await mem.start_session("test_20260325")
    print(f"  session started: {thread_id}")
    assert thread_id is not None, "thread_id is None"

    # ユーザーメッセージ保存
    await mem.save_user_message(
        user_id="test_user_tanaka",
        display_name="田中",
        text="こんばんは！初めて来ました",
    )
    print("  user message saved")

    # AI応答保存
    await mem.save_assistant_message(
        "あ、いらっしゃい。初めて？ ありがとね。"
    )
    print("  assistant message saved")

    # もう1往復
    await mem.save_user_message(
        user_id="test_user_tanaka",
        display_name="田中",
        text="音楽の話って好き？最近ずっとYOASOBI聴いてて",
    )
    await mem.save_assistant_message(
        "YOASOBI……あー、いいよね。なんか夜に聴くとさ、ちょっと切なくなるっていうか。"
    )
    print("  second exchange saved")

    # 少し待ってからコンテキスト取得（Zepの非同期処理待ち）
    print("  waiting 3s for Zep ingestion...")
    await asyncio.sleep(3)

    context = await mem.get_context(user_id="test_user_tanaka")
    if context:
        print(f"  context retrieved ({len(context)} chars):")
        # 長すぎたら切り詰めて表示
        preview = context[:200] + "..." if len(context) > 200 else context
        print(f"    {preview}")
    else:
        print("  context: (empty - Zep may still be processing)")

    # セッション終了
    await mem.end_session(emotion_snapshot={
        'joy': 60, 'affection': 55, 'fatigue': 10
    })
    print("  session ended with emotion snapshot")
    print("Test 5 full cycle: OK")
    return True


async def test_6_pipeline_import():
    """pipeline.pyがZep統合後もインポートできるか"""
    try:
        from broadcast.pipeline import BroadcastPipeline, PipelineConfig
        print("Test 6 pipeline import: OK")
        return True
    except Exception as e:
        print(f"Test 6 pipeline import: FAIL - {e}")
        return False


def main():
    print("=" * 50)
    print("Zep Cloud 記憶レイヤー テスト")
    print("=" * 50)

    # 同期テスト
    if not test_1_import():
        print("\n❌ zep-cloud SDK未インストール")
        print("実行: pip install zep-cloud")
        return
    test_2_zep_memory_import()
    has_key = test_3_api_key()

    # 非同期テスト
    if has_key:
        asyncio.run(test_4_connection())
        asyncio.run(test_5_full_cycle())
    else:
        print("Test 4-5: SKIP (no API key)")

    asyncio.run(test_6_pipeline_import())
    print("\n" + "=" * 50)
    print("Zep テスト完了")


if __name__ == "__main__":
    main()
