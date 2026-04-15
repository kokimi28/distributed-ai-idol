# memory/zep_client.py
"""
Zep Cloud 記憶レイヤー

Stage 4（海馬 = エピソード記憶）を担当。
- ユーザー管理: 視聴者を自動登録
- スレッド管理: 配信セッション = Zepスレッド
- メッセージ保存: コメント + AI応答を非同期保存
- コンテキスト取得: 関連する事実・エンティティをLLMプロンプトに注入
- グラフデータ: 感情スナップショット・関係性データ

使い方:
    mem = ZepMemory()
    await mem.initialize()
    await mem.start_session("broadcast_20260325_2100")
    await mem.save_user_message("user123", "田中", "こんばんは！")
    context = await mem.get_context()
    await mem.save_assistant_message("うん、こんばんは。来てくれたんだ。")
    await mem.end_session(emotion_snapshot={...})
"""

import os
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


# Zep Cloud SDK
try:
    from zep_cloud.client import AsyncZep
    from zep_cloud.types import Message as ZepMessage
    ZEP_AVAILABLE = True
except ImportError:
    ZEP_AVAILABLE = False
    logger.warning("zep-cloud not installed. Memory disabled.")


class ZepMemory:
    """Zep Cloud記憶レイヤー。パイプラインから非同期で呼ばれる。"""

    def __init__(self, character_name: str = "まお"):
        self._api_key = os.getenv("ZEP_API_KEY", "")
        self._client: Optional[AsyncZep] = None
        self._character_name = character_name

        # 現在のセッション
        self._thread_id: Optional[str] = None
        self._session_label: Optional[str] = None

        # ユーザーキャッシュ（同一配信内で重複登録を防ぐ）
        self._known_users: set[str] = set()

        # 有効かどうか
        self._enabled = False

    async def initialize(self) -> bool:
        """Zep Cloudクライアントを初期化する。"""
        if not ZEP_AVAILABLE:
            logger.info("Zep SDK not available. Memory layer disabled.")
            return False
        if not self._api_key:
            logger.info("ZEP_API_KEY not set. Memory layer disabled.")
            return False

        try:
            self._client = AsyncZep(api_key=self._api_key)
            self._enabled = True
            logger.info("Zep Cloud connected.")
            return True
        except Exception as e:
            logger.error(f"Zep init failed: {e}")
            return False

    @property
    def is_enabled(self) -> bool:
        return self._enabled and self._client is not None

    # ── セッション管理 ────────────────────────────────

    async def start_session(self, session_label: str, user_id: str = "broadcast") -> Optional[str]:
        """配信セッション開始時にZepスレッドを作成する。"""
        if not self.is_enabled:
            return None

        self._session_label = session_label
        self._thread_id = f"broadcast_{session_label}_{uuid.uuid4().hex[:8]}"
        self._known_users.clear()

        try:
            # 配信用ユーザー（AI側）を確保
            await self._ensure_user(
                user_id="ai_idol",
                first_name=self._character_name,
                last_name="(AI)",
            )
            # スレッド作成
            await self._client.thread.create(
                thread_id=self._thread_id,
                user_id="ai_idol",
            )
            logger.info(f"Zep thread created: {self._thread_id}")
            return self._thread_id
        except Exception as e:
            logger.error(f"Zep start_session failed: {e}")
            return None

    async def end_session(self, emotion_snapshot: dict = None) -> None:
        """配信終了時に感情スナップショットをグラフに保存する。"""
        if not self.is_enabled or not self._thread_id:
            return

        if emotion_snapshot:
            try:
                snapshot_text = (
                    f"配信「{self._session_label}」終了時の感情状態: "
                    + json.dumps(emotion_snapshot, ensure_ascii=False)
                )
                await self._client.graph.add(
                    user_id="ai_idol",
                    type="text",
                    data=snapshot_text,
                )
            except Exception as e:
                logger.error(f"Zep end_session graph.add failed: {e}")

        self._thread_id = None
        self._session_label = None

    # ── ユーザー管理 ──────────────────────────────────

    async def _ensure_user(self, user_id: str,
                           first_name: str = "",
                           last_name: str = "") -> None:
        """ユーザーが存在しなければ作成する。"""
        if user_id in self._known_users:
            return

        try:
            await self._client.user.add(
                user_id=user_id,
                first_name=first_name or user_id,
                last_name=last_name,
            )
        except Exception:
            # 既に存在する場合は409が返る → 無視
            pass

        self._known_users.add(user_id)

    # ── メッセージ保存 ────────────────────────────────

    async def save_user_message(self, user_id: str,
                                display_name: str,
                                text: str,
                                is_superchat: bool = False) -> None:
        """視聴者コメントをZepに保存する。"""
        if not self.is_enabled or not self._thread_id:
            return

        try:
            await self._ensure_user(user_id, first_name=display_name)

            content = text
            if is_superchat:
                content = f"[スーパーチャット] {text}"

            messages = [ZepMessage(
                created_at=datetime.now(timezone.utc).isoformat(),
                name=display_name,
                role="user",
                content=content,
            )]
            await self._client.thread.add_messages(
                self._thread_id, messages=messages
            )
        except Exception as e:
            logger.debug(f"Zep save_user_message failed: {e}")

    async def save_assistant_message(self, text: str) -> None:
        """AI応答をZepに保存する。"""
        if not self.is_enabled or not self._thread_id:
            return

        try:
            messages = [ZepMessage(
                created_at=datetime.now(timezone.utc).isoformat(),
                name=self._character_name,
                role="assistant",
                content=text,
            )]
            await self._client.thread.add_messages(
                self._thread_id, messages=messages
            )
        except Exception as e:
            logger.debug(f"Zep save_assistant_message failed: {e}")

    # ── コンテキスト取得（LLM注入用）──────────────────

    async def get_context(self, user_id: str = None) -> str:
        """
        現在のスレッドから関連コンテキストを取得する。
        Zepが知識グラフから事実・エンティティを自動抽出して返す。

        Returns:
            str: LLMプロンプトに注入するコンテキスト文字列。
                 取得できない場合は空文字列。
        """
        if not self.is_enabled or not self._thread_id:
            return ""

        try:
            memory = await self._client.thread.get_user_context(
                thread_id=self._thread_id,
            )
            context = getattr(memory, 'context', '')
            if context:
                return f"\n【視聴者の記憶（Zep）】\n{context}\n"
            return ""
        except Exception as e:
            logger.debug(f"Zep get_context failed: {e}")
            return ""

    async def save_relationship_event(self, user_id: str,
                                       display_name: str,
                                       event_text: str) -> None:
        """
        関係性イベントをグラフに直接追加する。
        例: 「田中さんが3回連続で配信に来た」
        例: 「山田さんがスーパーチャットを送った」
        """
        if not self.is_enabled:
            return

        try:
            await self._client.graph.add(
                user_id=user_id,
                type="text",
                data=event_text,
            )
        except Exception as e:
            logger.debug(f"Zep save_relationship_event failed: {e}")

    async def search_user_facts(self, user_id: str,
                                 query: str,
                                 limit: int = 5) -> list[str]:
        """
        特定ユーザーの知識グラフを検索する。
        例: search_user_facts("user123", "好きな音楽")
        """
        if not self.is_enabled:
            return []

        try:
            results = await self._client.graph.search(
                user_id=user_id,
                query=query,
                limit=limit,
            )
            facts = []
            for edge in (results.edges or []):
                if hasattr(edge, 'fact') and edge.fact:
                    facts.append(edge.fact)
            return facts
        except Exception as e:
            logger.debug(f"Zep search_user_facts failed: {e}")
            return []
