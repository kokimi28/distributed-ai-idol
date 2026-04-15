# broadcast/youtube_chat.py  YouTube Live Chat ポーリング
"""
YouTube Live Chat APIからコメントを取得し、pipeline.on_comment()に流す。
asyncioタスクとしてイベントループに参加する。

API Quota: liveChatMessages.list = 5 units/call
  10,000 units/day → 2,000 calls → 約2.8時間分（5s間隔）
  pollingIntervalMs（API側指定）に従うことでquotaを節約。
"""

import os
import asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Optional
from dotenv import load_dotenv
from googleapiclient.discovery import build
from loguru import logger

load_dotenv()


@dataclass
class ChatComment:
    """パイプラインに渡すコメントオブジェクト"""
    author: str
    text: str
    timestamp: datetime
    is_member: bool = False
    is_superchat: bool = False
    superchat_amount: float = 0.0
    raw: dict = field(default_factory=dict, repr=False)


class YouTubeChatPoller:
    """YouTube Live Chat のポーリングを管理"""

    def __init__(
        self,
        on_comment: Callable[[ChatComment], Awaitable[None]],
        api_key: Optional[str] = None,
        channel_id: Optional[str] = None,
    ):
        self._api_key = api_key or os.getenv('YOUTUBE_API_KEY')
        self._channel_id = channel_id or os.getenv('YOUTUBE_CHANNEL_ID')
        self._on_comment = on_comment
        self._youtube = None
        self._live_chat_id: Optional[str] = None
        self._page_token: Optional[str] = None
        self._polling_interval: float = 5.0  # 初期値、APIレスポンスで更新
        self._running = False
        self._total_comments = 0

    # === Public API ===

    async def start(self, live_chat_id: Optional[str] = None):
        """ポーリング開始。live_chat_idを直接渡すかauto-detectする"""
        self._youtube = build('youtube', 'v3', developerKey=self._api_key)

        if live_chat_id:
            # videoIdが渡された場合は自動変換
            if len(live_chat_id) <= 15 and not live_chat_id.startswith('Cg'):
                logger.info(f'videoIdと判定 → liveChatIdに変換中: {live_chat_id}')
                converted = self._video_id_to_chat_id(live_chat_id)
                if converted:
                    self._live_chat_id = converted
                else:
                    logger.error('videoIdからliveChatIdへの変換失敗')
                    return False
            else:
                self._live_chat_id = live_chat_id
        else:
            self._live_chat_id = self._find_live_chat_id()

        if not self._live_chat_id:
            logger.warning('ライブ配信が見つかりません。配信開始後に再試行してください')
            return False

        logger.info(f'YouTube Chat接続OK: liveChatId={self._live_chat_id}')
        self._running = True
        return True

    async def poll_loop(self):
        """メインポーリングループ（asyncioタスクとして実行）"""
        if not self._running:
            logger.error('start() を先に呼んでください')
            return

        logger.info(f'YouTube Chatポーリング開始（間隔: {self._polling_interval}s）')

        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                err_str = str(e)
                if 'pageTokenInvalid' in err_str or 'page token' in err_str.lower():
                    logger.warning('pageToken無効 → リセットして再試行')
                    self._page_token = None
                    await asyncio.sleep(3)
                    continue
                logger.error(f'ポーリングエラー: {e}')
                # API制限やネットワークエラー時は長めに待つ
                await asyncio.sleep(30)
                continue

            await asyncio.sleep(self._polling_interval)

    def stop(self):
        """ポーリング停止"""
        self._running = False
        logger.info(f'YouTube Chatポーリング停止（合計: {self._total_comments}コメント処理）')

    # === Internal ===

    def _video_id_to_chat_id(self, video_id: str) -> Optional[str]:
        """videoIdからliveChatIdを取得する"""
        try:
            resp = self._youtube.videos().list(
                part='liveStreamingDetails',
                id=video_id,
            ).execute()
            items = resp.get('items', [])
            if not items:
                return None
            live_details = items[0].get('liveStreamingDetails', {})
            chat_id = live_details.get('activeLiveChatId')
            if chat_id:
                logger.info(f'liveChatId取得成功: {chat_id[:20]}...')
            return chat_id
        except Exception as e:
            logger.error(f'videoId→liveChatId変換失敗: {e}')
            return None

    def _find_live_chat_id(self) -> Optional[str]:
        """チャンネルの現在のライブ配信からliveChatIdを取得"""
        if not self._channel_id:
            logger.warning('YOUTUBE_CHANNEL_ID が未設定')
            return None

        # Step 1: ライブ配信を検索（quota: 100 units）
        search_resp = self._youtube.search().list(
            part='id',
            channelId=self._channel_id,
            eventType='live',
            type='video',
            maxResults=1,
        ).execute()

        items = search_resp.get('items', [])
        if not items:
            return None

        video_id = items[0]['id']['videoId']

        # Step 2: 動画のliveChatIdを取得（quota: 1 unit）
        video_resp = self._youtube.videos().list(
            part='liveStreamingDetails',
            id=video_id,
        ).execute()

        video_items = video_resp.get('items', [])
        if not video_items:
            return None

        live_details = video_items[0].get('liveStreamingDetails', {})
        return live_details.get('activeLiveChatId')

    async def _poll_once(self):
        """1回分のポーリング（quota: 5 units）"""
        params = {
            'liveChatId': self._live_chat_id,
            'part': 'snippet,authorDetails',
            'maxResults': 200,
        }
        if self._page_token:
            params['pageToken'] = self._page_token

        # API呼び出し（同期→非同期ラップ）
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._youtube.liveChatMessages().list(**params).execute()
        )

        # ポーリング間隔を更新（API側が指定する値に従う）
        interval_ms = resp.get('pollingIntervalMillis', 5000)
        self._polling_interval = interval_ms / 1000.0

        # pageToken更新（次回は新しいメッセージだけ取得）
        self._page_token = resp.get('nextPageToken')

        # コメント処理
        for item in resp.get('items', []):
            comment = self._parse_comment(item)
            if comment:
                self._total_comments += 1
                try:
                    await self._on_comment(comment)
                except Exception as e:
                    logger.error(f'コメント処理エラー: {e}')

    def _parse_comment(self, item: dict) -> Optional[ChatComment]:
        """APIレスポンスのitemをChatCommentに変換"""
        snippet = item.get('snippet', {})
        author = item.get('authorDetails', {})
        msg_type = snippet.get('type', '')

        # テキストメッセージとスーパーチャットのみ処理
        if msg_type == 'textMessageEvent':
            return ChatComment(
                author=author.get('displayName', ''),
                text=snippet.get('textMessageDetails', {}).get('messageText', ''),
                timestamp=_parse_ts(snippet.get('publishedAt', '')),
                is_member=author.get('isChatMember', False),
                raw=item,
            )
        elif msg_type == 'superChatEvent':
            details = snippet.get('superChatDetails', {})
            return ChatComment(
                author=author.get('displayName', ''),
                text=details.get('userComment', ''),
                timestamp=_parse_ts(snippet.get('publishedAt', '')),
                is_member=author.get('isChatMember', False),
                is_superchat=True,
                superchat_amount=float(details.get('amountMicros', 0)) / 1_000_000,
                raw=item,
            )
        return None


def _parse_ts(ts_str: str) -> datetime:
    """ISO 8601文字列をdatetimeに変換"""
    if not ts_str:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except ValueError:
        return datetime.now(timezone.utc)