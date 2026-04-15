# broadcast/vtube_control.py
"""
VTube Studio 表情制御

WebSocket APIでVTube StudioのLive2Dパラメータを感情状態に連動させる。
感情→表情のマッピングと、発話中の口パク制御を担当。

VTube Studio API:
- WebSocket: ws://localhost:8001
- 認証→パラメータ注入の2ステップ
- ドキュメント: https://github.com/DenchiSoft/VTubeStudio
"""

import os
import json
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from shared.config_store import config

try:
    import websockets
except ImportError:
    websockets = None


# ── 感情→Live2Dパラメータのマッピング ──────────────────

# VTube StudioのカスタムパラメータID
# ※実際のモデルに合わせて調整が必要
@dataclass
class FaceExpression:
    """Live2D表情パラメータ（0.0-1.0）"""
    eye_open_left: float = 1.0
    eye_open_right: float = 1.0
    eye_smile_left: float = 0.0
    eye_smile_right: float = 0.0
    brow_left_y: float = 0.0       # 正=上がる 負=下がる
    brow_right_y: float = 0.0
    mouth_open: float = 0.0
    mouth_smile: float = 0.0       # 正=笑顔 負=への字
    face_angle_x: float = 0.0      # 顔の左右傾き
    face_angle_z: float = 0.0      # 顔の回転
    body_angle_x: float = 0.0      # 体の傾き
    cheek_blush: float = 0.0       # 頬の赤み


# 感情別の表情オフセット fallback
_FALLBACK_EMOTION_FACE_MAP: dict[str, dict[str, float]] = {
    'joy': {
        'eye_smile_left': 0.8,
        'eye_smile_right': 0.8,
        'mouth_smile': 0.7,
        'brow_left_y': 0.2,
        'brow_right_y': 0.2,
        'body_angle_x': 0.05,
    },
    'sadness': {
        'eye_open_left': -0.3,
        'eye_open_right': -0.3,
        'brow_left_y': -0.4,
        'brow_right_y': -0.3,
        'mouth_smile': -0.3,
        'face_angle_z': -0.05,
    },
    'anger': {
        'brow_left_y': -0.6,
        'brow_right_y': -0.5,
        'eye_open_left': 0.2,
        'mouth_smile': -0.5,
    },
    'surprise': {
        'eye_open_left': 0.5,
        'eye_open_right': 0.5,
        'brow_left_y': 0.6,
        'brow_right_y': 0.6,
        'mouth_open': 0.4,
    },
    'fear': {
        'eye_open_left': 0.3,
        'eye_open_right': 0.3,
        'brow_left_y': 0.3,
        'brow_right_y': -0.2,
        'body_angle_x': -0.1,
    },
    'embarrass': {
        'eye_open_left': -0.2,
        'face_angle_z': -0.1,
        'cheek_blush': 0.8,
        'mouth_smile': 0.2,
    },
    'affection': {
        'eye_smile_left': 0.5,
        'eye_smile_right': 0.5,
        'mouth_smile': 0.4,
        'cheek_blush': 0.3,
        'face_angle_z': 0.05,
    },
    'fatigue': {
        'eye_open_left': -0.4,
        'eye_open_right': -0.4,
        'brow_left_y': -0.2,
        'brow_right_y': -0.2,
        'body_angle_x': -0.08,
    },
    'loneliness': {
        'eye_open_left': -0.2,
        'eye_open_right': -0.2,
        'mouth_smile': -0.2,
        'face_angle_z': -0.08,
        'body_angle_x': -0.05,
    },
}

# soto/uchi の表情抑制 fallback
_FALLBACK_EXPRESSION_SUPPRESSION = {
    'broadcast': 0.6,
    'private': 1.0,
}

def _get_vtube_config():
    """config_storeからVTubeパラメータを取得"""
    data = config.get_sync('vtube_params')
    if not data:
        return _FALLBACK_EMOTION_FACE_MAP, _FALLBACK_EXPRESSION_SUPPRESSION, None, None
    return (
        data.get('emotion_face_map', _FALLBACK_EMOTION_FACE_MAP),
        data.get('expression_suppression', _FALLBACK_EXPRESSION_SUPPRESSION),
        data.get('param_map'),
        data.get('range_map'),
    )


def emotion_to_expression(emotions: dict, mode: str = 'broadcast') -> FaceExpression:
    """
    感情状態辞書からLive2D表情パラメータを生成する。

    Args:
        emotions: {'joy': 80, 'sadness': 10, ...}
        mode: 'broadcast' or 'private'

    Returns:
        FaceExpression
    """
    expr = FaceExpression()
    face_map, suppression_map, _, _ = _get_vtube_config()
    suppression = suppression_map.get(mode, 0.8)

    for emotion, value in emotions.items():
        if emotion not in face_map or value <= 0:
            continue

        offsets = face_map[emotion]
        factor = (value / 100.0) * suppression

        for param, delta in offsets.items():
            current = getattr(expr, param, 0.0)
            setattr(expr, param, current + delta * factor)

    # クランプ
    for field_name in FaceExpression.__dataclass_fields__:
        val = getattr(expr, field_name)
        setattr(expr, field_name, max(-1.0, min(1.0, round(val, 3))))

    return expr


# ── VTube Studio WebSocket クライアント ─────────────────

class VTubeController:
    """
    VTube Studio APIクライアント。
    認証→パラメータ作成→パラメータ注入の流れで表情を制御する。
    """

    PLUGIN_NAME = "DistributedAIIdol"
    PLUGIN_DEVELOPER = "AIIdolProject"

    def __init__(self, host: str = "localhost", port: int = 8001):
        self.uri = f"ws://{host}:{port}"
        self._ws = None
        self._auth_token: Optional[str] = None
        self._request_id = 0
        self._registered_params: set = set()

    async def connect(self) -> bool:
        """VTube Studioに接続し、認証する"""
        if websockets is None:
            raise ImportError("websockets パッケージが必要です")

        try:
            self._ws = await websockets.connect(self.uri)
        except Exception as e:
            return False

        # 認証リクエスト
        auth_resp = await self._send({
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": self._next_id(),
            "messageType": "AuthenticationTokenRequest",
            "data": {
                "pluginName": self.PLUGIN_NAME,
                "pluginDeveloper": self.PLUGIN_DEVELOPER,
            },
        })

        if auth_resp and auth_resp.get("data", {}).get("authenticationToken"):
            self._auth_token = auth_resp["data"]["authenticationToken"]

            # トークンで認証
            auth2 = await self._send({
                "apiName": "VTubeStudioPublicAPI",
                "apiVersion": "1.0",
                "requestID": self._next_id(),
                "messageType": "AuthenticationRequest",
                "data": {
                    "pluginName": self.PLUGIN_NAME,
                    "pluginDeveloper": self.PLUGIN_DEVELOPER,
                    "authenticationToken": self._auth_token,
                },
            })
            return auth2 and auth2.get("data", {}).get("authenticated", False)

        return False

    async def disconnect(self):
        """接続を閉じる"""
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _send(self, payload: dict) -> Optional[dict]:
        """WebSocketでメッセージを送受信"""
        if not self._ws:
            return None
        try:
            await self._ws.send(json.dumps(payload))
            response = await asyncio.wait_for(self._ws.recv(), timeout=5.0)
            return json.loads(response)
        except Exception:
            return None

    def _next_id(self) -> str:
        self._request_id += 1
        return f"req_{self._request_id}"

    async def register_custom_parameter(self, param_name: str,
                                         min_val: float = -1.0,
                                         max_val: float = 1.0,
                                         default: float = 0.0):
        """カスタムパラメータを登録（初回のみ）"""
        if param_name in self._registered_params:
            return

        await self._send({
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": self._next_id(),
            "messageType": "ParameterCreationRequest",
            "data": {
                "parameterName": param_name,
                "explanation": f"AI Idol emotion param: {param_name}",
                "min": min_val,
                "max": max_val,
                "defaultValue": default,
            },
        })
        self._registered_params.add(param_name)

    async def apply_expression(self, expression: FaceExpression):
        """FaceExpressionをVTube Studioに適用する"""
        if not self._ws:
            return

        # パラメータ名のマッピング（config_storeから取得、fallback付き）
        _, _, db_param_map, db_range_map = _get_vtube_config()

        param_map = db_param_map or {
            'eye_open_left': 'EyeOpenLeft',
            'eye_open_right': 'EyeOpenRight',
            'eye_smile_left': 'EyeOpenLeft',
            'eye_smile_right': 'EyeOpenRight',
            'brow_left_y': 'BrowLeftY',
            'brow_right_y': 'BrowRightY',
            'mouth_open': 'MouthOpen',
            'mouth_smile': 'MouthSmile',
            'face_angle_x': 'FaceAngleX',
            'face_angle_z': 'FaceAngleZ',
            'body_angle_x': 'MocopiBodyAngleX',
            'cheek_blush': 'CheekPuff',
        }

        range_map = {}
        if db_range_map:
            for k, v in db_range_map.items():
                if isinstance(v, list) and len(v) == 2:
                    range_map[k] = tuple(v)
        else:
            range_map = {
                'FaceAngleX': (-30.0, 30.0),
                'FaceAngleZ': (-90.0, 90.0),
                'MocopiBodyAngleX': (-10.0, 10.0),
            }

        params = []
        smile_reduction = {}  # eye_smile → eye_openの減算を記録
        for field_name, vts_name in param_map.items():
            value = getattr(expression, field_name, 0.0)

            # eye_smile は EyeOpen を下げることで表現（目を細める）
            if field_name in ('eye_smile_left', 'eye_smile_right'):
                smile_reduction[vts_name] = value * 0.5
                continue

            # レンジ変換（-1~1 → モデルのレンジ）
            if vts_name in range_map:
                mn, mx = range_map[vts_name]
                mid = (mn + mx) / 2.0
                half = (mx - mn) / 2.0
                value = mid + value * half
            else:
                # 0~1レンジのパラメータ: クランプ
                value = max(0.0, min(1.0, value))

            params.append({
                "id": vts_name,
                "value": value,
            })

        # eye_smile による EyeOpen 減算を適用
        for p in params:
            if p["id"] in smile_reduction:
                p["value"] = max(0.0, p["value"] - smile_reduction[p["id"]])

        await self._send({
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": self._next_id(),
            "messageType": "InjectParameterDataRequest",
            "data": {
                "parameterValues": params,
            },
        })

    async def set_mouth_open(self, value: float):
        """口パク制御（音声再生中に呼ぶ）"""
        if not self._ws:
            return
        await self._send({
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": self._next_id(),
            "messageType": "InjectParameterDataRequest",
            "data": {
                "parameterValues": [
                    {"id": "MouthOpen", "value": max(0.0, min(1.0, value))},
                ],
            },
        })

    async def hold_expression(self, expression: 'FaceExpression',
                               duration: float = 5.0, interval: float = 0.15):
        """表情を一定時間連続注入して維持する（トラッキング上書き対策）"""
        if not self._ws:
            return
        steps = int(duration / interval)
        for _ in range(steps):
            await self.apply_expression(expression)
            await asyncio.sleep(interval)

    @property
    def is_connected(self) -> bool:
        if self._ws is None:
            return False
        try:
            # websockets v13+: use .state
            from websockets.protocol import State
            return self._ws.state is State.OPEN
        except (ImportError, AttributeError):
            # websockets v12以前: use .open
            return getattr(self._ws, 'open', False)
