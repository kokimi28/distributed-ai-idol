import math
from datetime import datetime
from shared.config_store import config

_FALLBACK_HALF_LIVES = {
    'joy':        0.5,
    'sadness':    2.0,
    'anger':      0.17,
    'surprise':   0.08,
    'embarrass':  0.25,
    'fear':       0.17,
    'affection':  168.0,
    'loneliness': 1.0,
    'tension':    0.5,
    'fatigue':    8.0,
}

def _get_half_lives() -> dict:
    data = config.get_sync('emotion_half_lives')
    return data if data else _FALLBACK_HALF_LIVES

def calc_emotion_residue(prev_emotions: dict,
                          session_end_time: datetime) -> dict:
    if not prev_emotions or not session_end_time:
        return {}
    hours_elapsed = (datetime.now() - session_end_time).total_seconds() / 3600
    half_lives = _get_half_lives()
    residue = {}
    for emotion, value in prev_emotions.items():
        half_life = half_lives.get(emotion, 1.0)
        decay_factor = math.pow(0.5, hours_elapsed / half_life)
        residue[emotion] = int(value * decay_factor)
    return residue

def apply_residue_to_initial_state(initial_state: dict,
                                    residue: dict) -> dict:
    for emotion, residue_val in residue.items():
        current = initial_state.get(emotion, 0)
        initial_state[emotion] = min(100, current + min(residue_val, 50))
    return initial_state