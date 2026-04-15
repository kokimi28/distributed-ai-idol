# brain/reflex_layer.py  Stage 1: 感情反射（ルールベース）
"""
v4設計書に基づく反射層。LeDoux（1996）の扁桃体バイパス理論に対応。
入力テキストへの即時感情反射（<20ms目標）。
SmartPickerのプリコンパイルregexを使用して高速マッチング。
"""

import os
from dataclasses import dataclass
from shared.smart_picker import picker

@dataclass
class EmotionSpike:
    surprise: int = 0
    defensiveness: int = 0
    warmth: int = 0
    attention: int = 0
    loneliness: int = 0
    joy_reflex: int = 0
    fear_reflex: int = 0

SILENCE_THRESHOLD = float(os.getenv('REFLEX_SILENCE_MINUTES_THRESHOLD', '30'))

def apply_reflex(text: str, silence_minutes: float = 0) -> EmotionSpike:
    """Stage 1: 入力テキストへの即時感情反射（<20ms目標）
    SmartPickerのプリコンパイルregexを使用"""
    spike = EmotionSpike()
    matches = picker.match_reflex(text)
    for emotion, amount in matches:
        current = getattr(spike, emotion, 0)
        setattr(spike, emotion, current + amount)
    if silence_minutes > SILENCE_THRESHOLD:
        spike.loneliness += min(int(silence_minutes / 10), 40)
    return spike

def merge_spike_to_state(state: dict, spike: EmotionSpike) -> dict:
    """反射スパイクを感情状態に加算（上限100）"""
    mapping = {
        'surprise':     spike.surprise,
        'anger':        spike.defensiveness,
        'joy':          spike.joy_reflex,
        'fear':         spike.fear_reflex,
        'loneliness':   spike.loneliness,
        'affection':    int(spike.warmth * 0.3),
    }
    for emotion, delta in mapping.items():
        state[emotion] = min(100, state.get(emotion, 0) + delta)
    return state
