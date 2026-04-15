# brain/stream_clock.py
"""
配信タイマー・フェーズ管理

配信の時間経過を追跡し、フェーズ（opening/main/closing）を判定する。
疲労蓄積・沈黙検知もここで管理。autonomous_talk のトリガーソース。
"""

import time
from dataclasses import dataclass, field
from enum import Enum


class StreamPhase(Enum):
    OPENING = "opening"       # 配信開始〜5分: 挨拶・導入
    MAIN = "main"             # 5分〜終了10分前: 本編
    CLOSING = "closing"       # 終了10分前〜: 締め・振り返り
    ENDED = "ended"


@dataclass
class StreamClock:
    """配信の時間状態を管理する"""

    planned_duration_minutes: float = 60.0   # 予定配信時間
    opening_minutes: float = 1.5             # opening フェーズの長さ（短く）
    closing_minutes: float = 5.0             # closing フェーズの長さ（終了前）

    # 内部状態
    _start_time: float = 0.0
    _last_speak_time: float = 0.0
    _last_comment_time: float = 0.0
    _total_speaks: int = 0
    _is_live: bool = False

    # 疲労パラメータ
    fatigue: float = 0.0                     # 0-100
    _fatigue_rate_per_minute: float = 0.8    # 毎分の疲労蓄積量
    _fatigue_comment_boost: float = -2.0     # コメントで少し回復

    def start(self):
        """配信開始"""
        now = time.time()
        self._start_time = now
        self._last_speak_time = now
        self._last_comment_time = now
        self._total_speaks = 0
        self._is_live = True
        self.fatigue = 0.0

        # 短い配信ではフェーズを自動スケール
        # opening + closing が全体の1/3を超えないようにする
        total = self.planned_duration_minutes
        if self.opening_minutes + self.closing_minutes > total * 0.6:
            self.opening_minutes = max(0.5, total * 0.15)
            self.closing_minutes = max(1.0, total * 0.25)

    def stop(self):
        """配信終了"""
        self._is_live = False

    @property
    def is_live(self) -> bool:
        return self._is_live

    @property
    def elapsed_minutes(self) -> float:
        """配信開始からの経過分数"""
        if not self._is_live:
            return 0.0
        return (time.time() - self._start_time) / 60.0

    @property
    def remaining_minutes(self) -> float:
        """残り分数（予定ベース）"""
        return max(0.0, self.planned_duration_minutes - self.elapsed_minutes)

    @property
    def phase(self) -> StreamPhase:
        """現在の配信フェーズ"""
        if not self._is_live:
            return StreamPhase.ENDED
        elapsed = self.elapsed_minutes
        if elapsed < self.opening_minutes:
            return StreamPhase.OPENING
        if self.remaining_minutes < self.closing_minutes:
            return StreamPhase.CLOSING
        return StreamPhase.MAIN

    @property
    def silence_seconds(self) -> float:
        """最終発話からの沈黙秒数"""
        if not self._is_live:
            return 0.0
        return time.time() - self._last_speak_time

    @property
    def comment_silence_seconds(self) -> float:
        """最終コメントからの秒数"""
        if not self._is_live:
            return 0.0
        return time.time() - self._last_comment_time

    def on_speak(self):
        """発話した時に呼ぶ"""
        self._last_speak_time = time.time()
        self._total_speaks += 1

    def on_comment(self):
        """コメントを受信した時に呼ぶ"""
        self._last_comment_time = time.time()
        # コメントで少し疲労回復（やり取りのエネルギー）
        self.fatigue = max(0.0, self.fatigue + self._fatigue_comment_boost)

    def tick(self) -> dict:
        """
        毎ループで呼ぶ。疲労更新と現在の状態をまとめて返す。

        Returns:
            dict: phase, elapsed_min, remaining_min, silence_sec,
                  comment_silence_sec, fatigue, total_speaks
        """
        if not self._is_live:
            return {'phase': StreamPhase.ENDED.value}

        # 疲労蓄積（時間ベース）
        # 配信後半ほど疲労が溜まりやすい（非線形）
        elapsed = self.elapsed_minutes
        fatigue_multiplier = 1.0 + (elapsed / self.planned_duration_minutes) * 0.5
        self.fatigue = min(100.0, self.fatigue
                          + self._fatigue_rate_per_minute / 60.0 * fatigue_multiplier)

        return {
            'phase': self.phase.value,
            'elapsed_min': round(elapsed, 1),
            'remaining_min': round(self.remaining_minutes, 1),
            'silence_sec': round(self.silence_seconds, 1),
            'comment_silence_sec': round(self.comment_silence_seconds, 1),
            'fatigue': round(self.fatigue, 1),
            'total_speaks': self._total_speaks,
        }

    def should_speak(self, silence_threshold: float = 10.0) -> bool:
        """沈黙が閾値を超えたら発話すべき"""
        return self._is_live and self.silence_seconds > silence_threshold
