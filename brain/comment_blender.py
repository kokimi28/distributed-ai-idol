# brain/comment_blender.py
"""
コメント割込み制御

自律発話中にコメントが来た時の振る舞いを判定する。
反射層のスパイク強度と現在の発話状態で「即切替/文の切れ目/織込み/キュー/スルー」を決定。

設計根拠:
- 自律発話エンジン設計書（2026-03-23）
- 反射層（brain/reflex_layer.py）のEmotionSpike連携
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from brain.reflex_layer import EmotionSpike


class BlendMode(Enum):
    IMMEDIATE = "immediate"       # 即座に切替（スパチャ/攻撃的/名指し）
    AT_BREAK = "at_break"         # 文の切れ目で切替（通常コメント・関連性あり）
    WEAVE_IN = "weave_in"         # 話題に織り込む（現話題と関連するコメント）
    QUEUE = "queue"               # キューに積む（現話題と無関連）
    IGNORE = "ignore"             # スルー（荒らし/重複/低優先）


@dataclass
class BlendDecision:
    """割込み判定の結果"""
    mode: BlendMode
    reason: str
    priority: int = 0             # 0-100。高いほど優先
    delay_seconds: float = 0.0    # 遅延（at_breakやqueueの場合）
    original_comment: str = ""
    spike: EmotionSpike = None


# ── スパイク強度の閾値 ──────────────────────────────────
_SPIKE_THRESHOLD_IMMEDIATE = 50   # この値以上で即座に切替
_SPIKE_THRESHOLD_BREAK = 20      # この値以上で文の切れ目切替


def _total_spike_intensity(spike: EmotionSpike) -> int:
    """スパイクの総強度を計算"""
    return (
        spike.surprise
        + spike.defensiveness
        + spike.warmth
        + spike.attention
        + spike.joy_reflex
        + spike.fear_reflex
    )


def _is_spam_or_duplicate(comment: str, recent_comments: list[str]) -> bool:
    """荒らし・重複判定（簡易版）"""
    # 同じコメントが直近にある
    if comment in recent_comments[-5:]:
        return True
    # 極端に短い or 意味のないコメント
    if len(comment.strip()) <= 1:
        return True
    return False


def judge(
    comment: str,
    spike: EmotionSpike,
    is_superchat: bool = False,
    is_mention: bool = False,
    current_topic: str = "",
    current_phase: str = "",
    comment_keywords: list[str] = None,
    topic_keywords: list[str] = None,
    recent_comments: list[str] = None,
) -> BlendDecision:
    """
    コメントの割込みモードを判定する。

    Args:
        comment: コメントテキスト
        spike: 反射層が生成したEmotionSpike
        is_superchat: スパチャか
        is_mention: 名指し（@キャラ名）か
        current_topic: 現在の話題
        current_phase: 現在の話題フェーズ
        comment_keywords: コメントから抽出したキーワード
        topic_keywords: 現在の話題のキーワード
        recent_comments: 直近のコメント履歴

    Returns:
        BlendDecision
    """
    recent = recent_comments or []
    c_keywords = comment_keywords or []
    t_keywords = topic_keywords or []

    intensity = _total_spike_intensity(spike)

    # ── 1. スルー判定（最初に弾く）──
    if _is_spam_or_duplicate(comment, recent):
        return BlendDecision(
            mode=BlendMode.IGNORE,
            reason='spam_or_duplicate',
            original_comment=comment,
            spike=spike,
        )

    # ── 2. 即座切替（最高優先）──
    # スパチャ・名指し・攻撃的コメント（defensiveness高）
    if is_superchat:
        return BlendDecision(
            mode=BlendMode.IMMEDIATE,
            reason='superchat',
            priority=100,
            original_comment=comment,
            spike=spike,
        )

    if spike.defensiveness >= _SPIKE_THRESHOLD_IMMEDIATE:
        return BlendDecision(
            mode=BlendMode.IMMEDIATE,
            reason='defensive_spike',
            priority=90,
            original_comment=comment,
            spike=spike,
        )

    if is_mention:
        return BlendDecision(
            mode=BlendMode.IMMEDIATE,
            reason='mention',
            priority=85,
            original_comment=comment,
            spike=spike,
        )

    if intensity >= _SPIKE_THRESHOLD_IMMEDIATE:
        return BlendDecision(
            mode=BlendMode.IMMEDIATE,
            reason='high_spike',
            priority=80,
            original_comment=comment,
            spike=spike,
        )

    # ── 3. 話題関連性チェック ──
    has_overlap = bool(set(c_keywords) & set(t_keywords)) if c_keywords and t_keywords else False

    # 関連性あり + スパイク中程度 → 織り込み
    if has_overlap and intensity >= _SPIKE_THRESHOLD_BREAK:
        return BlendDecision(
            mode=BlendMode.WEAVE_IN,
            reason='related_with_spike',
            priority=60,
            original_comment=comment,
            spike=spike,
        )

    # 関連性あり + スパイク低め → 文の切れ目で
    if has_overlap:
        return BlendDecision(
            mode=BlendMode.AT_BREAK,
            reason='related_low_spike',
            priority=50,
            delay_seconds=3.0,
            original_comment=comment,
            spike=spike,
        )

    # ── 4. 関連性なし ──
    # スパイク中程度 → 文の切れ目で
    if intensity >= _SPIKE_THRESHOLD_BREAK:
        return BlendDecision(
            mode=BlendMode.AT_BREAK,
            reason='unrelated_with_spike',
            priority=40,
            delay_seconds=5.0,
            original_comment=comment,
            spike=spike,
        )

    # スパイク低い → キューに積む
    return BlendDecision(
        mode=BlendMode.QUEUE,
        reason='unrelated_low_spike',
        priority=20,
        delay_seconds=15.0,
        original_comment=comment,
        spike=spike,
    )
