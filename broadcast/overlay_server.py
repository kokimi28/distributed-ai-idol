# broadcast/overlay_server.py
"""
OBSオーバーレイ用WebSocketサーバー

配信パイプラインの内部状態（感情・話題・コメントイベント）を
OBS Browser Sourceに配信する。

アーキテクチャ:
  pipeline.py → OverlayServer.broadcast() → WebSocket → OBS Browser Source(s)

プロトコル:
  JSON メッセージ、typeフィールドでイベント種類を区別:
  - state_update: 定期的な全状態更新（感情・話題・フェーズ・heat）
  - comment_event: コメント受信時（テキスト・ユーザー・反射スパイク）
  - topic_change: 話題切り替え時（新話題・キーワード）
  - phase_change: フェーズ遷移時（INTRO→DEVELOP等）

使い方:
  server = OverlayServer(port=8765)
  await server.start()
  server.broadcast_state(char_state, topic_info)
  server.broadcast_event('comment', {...})
  await server.stop()
"""

import asyncio
import json
import time
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Optional
from dataclasses import dataclass, asdict
from loguru import logger

try:
    import websockets
    from websockets.server import serve
except ImportError:
    import websockets
    serve = websockets.serve


class OverlayServer:
    """
    OBSオーバーレイへの状態配信サーバー。

    WebSocketで接続したクライアント（OBS Browser Source）に
    パイプラインの内部状態をリアルタイム配信する。
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._clients: set = set()
        self._server = None
        self._running = False
        self._last_state: dict = {}
        self._last_clip: dict = {}   # 最後のクリップ情報（新規接続に再送用）
        # 静的ファイルサーバー（動画・画像配信用）
        self._http_port = 8766
        self._http_server = None
        self._http_thread = None

    async def start(self):
        """WebSocketサーバー + HTTPファイルサーバーを起動"""
        try:
            self._server = await serve(
                self._handler, self.host, self.port
            )
            self._running = True
            logger.info(f'OverlayServer: ws://{self.host}:{self.port} で起動')
            # 静的ファイルサーバー起動（動画・画像をHTTPで配信）
            self._start_http_server()
            return True
        except OSError as e:
            logger.warning(f'OverlayServer: 起動失敗 ({e})')
            return False

    def _start_http_server(self):
        """プロジェクト全体をHTTPで配信（overlay HTML + 動画・画像キャッシュ）"""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        class ProjectHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=project_root, **kwargs)
            def log_message(self, format, *args):
                pass  # ログ抑制
            def end_headers(self):
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Accept-Ranges', 'bytes')
                super().end_headers()
            def do_GET(self):
                """Range Requestに対応（動画再生に必須）"""
                path = self.translate_path(self.path)
                if not os.path.isfile(path):
                    return super().do_GET()
                range_header = self.headers.get('Range')
                if not range_header or not range_header.startswith('bytes='):
                    return super().do_GET()
                file_size = os.path.getsize(path)
                range_spec = range_header[6:]  # 'bytes=' を除去
                parts = range_spec.split('-')
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if parts[1] else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1
                content_type = self.guess_type(path)
                self.send_response(206)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                self.send_header('Content-Length', str(length))
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-cache')
                super(SimpleHTTPRequestHandler, self).end_headers()
                with open(path, 'rb') as f:
                    f.seek(start)
                    self.wfile.write(f.read(length))

        try:
            self._http_server = HTTPServer(
                (self.host, self._http_port), ProjectHandler
            )
            self._http_thread = threading.Thread(
                target=self._http_server.serve_forever,
                daemon=True
            )
            self._http_thread.start()
            logger.info(
                f'FileServer: http://{self.host}:{self._http_port} '
                f'(serving {project_root})'
            )
        except OSError as e:
            logger.warning(f'FileServer: 起動失敗 ({e})')

    async def stop(self):
        """サーバーを停止"""
        self._running = False
        if self._http_server:
            self._http_server.shutdown()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        # 全クライアントを切断
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()
        logger.info('OverlayServer: 停止')

    async def _handler(self, websocket):
        """新しいクライアント接続のハンドラ"""
        self._clients.add(websocket)
        client_addr = websocket.remote_address
        logger.info(f'OverlayServer: クライアント接続 {client_addr} (合計{len(self._clients)})')

        # 接続時に最新状態を即送信
        if self._last_state:
            try:
                await websocket.send(json.dumps(self._last_state))
            except Exception:
                pass
        if self._last_clip:
            try:
                await websocket.send(json.dumps(self._last_clip))
            except Exception:
                pass

        try:
            async for message in websocket:
                # クライアントからのメッセージ（将来の拡張用）
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info(f'OverlayServer: クライアント切断 (残り{len(self._clients)})')

    def broadcast_state(self, char_state: dict, topic_info: dict,
                        clock_info: dict = None):
        """
        全状態更新をブロードキャスト。
        pipeline._play_prepared後やtick毎に呼ばれる想定。
        """
        msg = {
            'type': 'state_update',
            'timestamp': time.time(),
            'emotions': char_state,
            'topic': topic_info.get('topic', ''),
            'phase': topic_info.get('phase', ''),
            'heat': topic_info.get('heat', 0),
        }
        if clock_info:
            msg['elapsed_min'] = clock_info.get('elapsed_min', 0)
            msg['fatigue'] = clock_info.get('fatigue', 0)
            msg['comment_silence_sec'] = clock_info.get('comment_silence_sec', 0)

        self._last_state = msg
        self._broadcast(msg)

    def broadcast_comment(self, text: str, user_id: str,
                          spike_type: str = '', spike_amount: int = 0,
                          is_superchat: bool = False):
        """コメント受信イベントをブロードキャスト"""
        msg = {
            'type': 'comment_event',
            'timestamp': time.time(),
            'text': text,
            'user_id': user_id,
            'spike_type': spike_type,
            'spike_amount': spike_amount,
            'is_superchat': is_superchat,
        }
        self._broadcast(msg)

    def broadcast_topic_change(self, topic: str, keywords: list = None,
                               image_url: str = ''):
        """話題切り替えイベントをブロードキャスト"""
        msg = {
            'type': 'topic_change',
            'timestamp': time.time(),
            'topic': topic,
            'keywords': keywords or [],
            'image_url': image_url,
        }
        self._broadcast(msg)

    def broadcast_phase_change(self, phase: str, topic: str, heat: int):
        """フェーズ遷移イベントをブロードキャスト"""
        msg = {
            'type': 'phase_change',
            'timestamp': time.time(),
            'phase': phase,
            'topic': topic,
            'heat': heat,
        }
        self._broadcast(msg)

    def broadcast_subtitle(self, text: str, topic: str = '',
                           phase: str = ''):
        """字幕テキストをブロードキャスト（発話ごとに呼ぶ）"""
        msg = {
            'type': 'subtitle',
            'timestamp': time.time(),
            'text': text,
            'topic': topic,
            'phase': phase,
        }
        self._broadcast(msg)

    def _broadcast(self, msg: dict):
        """全クライアントにメッセージ送信（非同期タスクを発行）"""
        # clip_batch/cutawayをキャッシュ（新規接続で再送用）
        if msg.get('type') in ('clip_batch', 'cutaway'):
            self._last_clip = msg
        if not self._clients:
            return
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self._clients):
            asyncio.ensure_future(self._safe_send(ws, data))

    async def _safe_send(self, ws, data: str):
        """エラーを握りつぶして送信"""
        try:
            await ws.send(data)
        except Exception:
            self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def is_running(self) -> bool:
        return self._running
