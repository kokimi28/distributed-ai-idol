# character/emotion_to_voice.py
"""
感情状態 → ElevenLabs音声パラメータ変換
設定データはconfig_store経由でDB/JSONから読み込み。
"""
from shared.config_store import config


# ── fallback（config_store未初期化時用）──
_FALLBACK_BASE = {
    'broadcast': {'stability': 0.55, 'similarity_boost': 0.70, 'style': 0.45, 'use_speaker_boost': True},
    'private': {'stability': 0.70, 'similarity_boost': 0.85, 'style': 0.25, 'use_speaker_boost': False},
}
_FALLBACK_SUPPRESSION = {'broadcast': 0.6, 'private': 1.0}

_FALLBACK_EMOTION_INFLUENCE = {
    'joy':        {'stability': -0.45, 'similarity_boost': -0.10, 'style': 0.40},
    'sadness':    {'stability': 0.30, 'similarity_boost': 0.10, 'style': -0.20},
    'anger':      {'stability': -0.35, 'similarity_boost': -0.15, 'style': 0.30},
    'surprise':   {'stability': -0.50, 'similarity_boost': -0.05, 'style': 0.35},
    'fear':       {'stability': -0.25, 'similarity_boost': 0.05, 'style': -0.10},
    'embarrass':  {'stability': -0.20, 'similarity_boost': 0.10, 'style': -0.15},
    'affection':  {'stability': 0.10, 'similarity_boost': 0.15, 'style': 0.10},
    'fatigue':    {'stability': 0.25, 'similarity_boost': 0.10, 'style': -0.30},
    'tension':    {'stability': -0.15, 'similarity_boost': 0.05, 'style': 0.10},
    'loneliness': {'stability': 0.15, 'similarity_boost': 0.10, 'style': -0.15},
}

def _get_voice_settings():
    """config_storeから音声設定を取得"""
    data = config.get_sync('voice_settings')
    if data:
        return (
            data.get('base', _FALLBACK_BASE),
            data.get('emotion_influence', _FALLBACK_EMOTION_INFLUENCE),
            data.get('suppression', _FALLBACK_SUPPRESSION),
        )
    return _FALLBACK_BASE, _FALLBACK_EMOTION_INFLUENCE, _FALLBACK_SUPPRESSION


def convert_emotion_to_voice(emotions: dict, mode: str) -> dict:
    """
    感情状態辞書とモードからElevenLabs音声パラメータを生成する。

    Args:
        emotions: 感情名→値(0-100)の辞書 例: {'joy': 80, 'sadness': 10}
        mode: 'broadcast' または 'private'

    Returns:
        dict: stability, similarity_boost, style, use_speaker_boost
    """
    if mode not in ('broadcast', 'private'):
        mode = 'private'

    base_settings, emotion_influence, suppression_map = _get_voice_settings()

    # ベースラインをコピー
    params = dict(base_settings.get(mode, base_settings.get('private', {})))
    suppression = suppression_map.get(mode, 1.0)

    # 各感情の影響を加算
    for emotion, value in emotions.items():
        if emotion not in emotion_influence or value <= 0:
            continue

        influence = emotion_influence[emotion]
        # 正規化（value/100）× 抑制係数 × 影響量
        factor = (value / 100.0) * suppression

        for param, delta in influence.items():
            if param in params and isinstance(params[param], (int, float)):
                params[param] += delta * factor

    # クランプ（0.0〜1.0）
    for key in ('stability', 'similarity_boost', 'style'):
        params[key] = max(0.0, min(1.0, round(params[key], 3)))

    return params
