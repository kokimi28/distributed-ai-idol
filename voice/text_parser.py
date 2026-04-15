# voice/text_parser.py
"""
非言語タグパーサー

LLM出力のフィラータグ（ふふっ）を括弧だけ外して本文に溶かし込む。
分割するのは【間】【長間】だけ。

設計方針：
- フィラーは分割しない。括弧を外して本文の一部として一括合成
- これにより声質・音圧・ピッチが完全に統一される
- 【間】【長間】のみがテキストの分割点

入力例:
  「（ふふっ）あのさ、聞いてよ。【間】最近気になったんだけど……」
出力:
  [
    Segment(type="speech", text="ふふっ、あのさ、聞いてよ。"),
    Segment(type="silence", duration_ms=800),
    Segment(type="speech", text="最近気になったんだけど……"),
  ]
"""

import re
from dataclasses import dataclass


@dataclass
class Segment:
    """音声合成に渡す1セグメント"""
    type: str              # "speech" | "silence"
    text: str = ""
    duration_ms: int = 0


SILENCE_TAGS = {
    '【間】': 800,
    '【長間】': 1500,
}

_FILLER_PATTERN = re.compile(r'（([^）]+)）')
_SILENCE_PATTERN = re.compile(r'【(間|長間)】')


def parse_speech_text(text: str) -> list[Segment]:
    """フィラー括弧を外し、間タグだけで分割する"""
    # Step 1: フィラーの括弧を外す（中身はそのまま残る）
    cleaned = _FILLER_PATTERN.sub(r'\1', text)

    # Step 2: 間タグで分割
    segments = []
    parts = _SILENCE_PATTERN.split(cleaned)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part in ('間', '長間'):
            tag = f'【{part}】'
            segments.append(Segment(
                type="silence",
                duration_ms=SILENCE_TAGS.get(tag, 800),
            ))
        else:
            segments.append(Segment(type="speech", text=part))

    if not segments and text.strip():
        segments.append(Segment(
            type="speech",
            text=_FILLER_PATTERN.sub(r'\1', text).strip(),
        ))

    return segments
