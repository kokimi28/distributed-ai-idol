# shared/smart_picker.py
"""
スマートピッカー

フィラー・反射ルールの高速・高品質な選択を提供する。

機能:
1. 重複排除 — 最近使った項目を避ける（カテゴリ別の使用済みウィンドウ）
2. energyマッチング — 現在の疲労度・テンションに合うフィラーを優先
3. 正規表現プリコンパイル — 反射ルールのregexを起動時にコンパイル
4. O(1)キャッシュ — 全データは起動時にメモリに載る

パフォーマンス目標:
- pick_filler: <1ms
- match_reflex: <5ms（20+パターンのregex.search）
"""

import re
import random
from collections import deque
from typing import Optional
from shared.config_store import config


# energyレベルのマッピング
# fatigue 0-30: high, 31-60: mid, 61-100: low
def _fatigue_to_energy(fatigue: float) -> str:
    if fatigue < 30:
        return 'high'
    elif fatigue < 60:
        return 'mid'
    return 'low'


class SmartPicker:
    """フィラー・反射ルールのスマート選択エンジン"""

    def __init__(self, no_repeat_window: int = 5):
        self._no_repeat_window = no_repeat_window
        # カテゴリ別の最近使った項目（重複排除用）
        self._recent: dict[str, deque] = {}
        # プリコンパイル済みの反射ルール
        self._compiled_rules: list[tuple] = []  # [(compiled_re, emotion, amount)]
        self._initialized = False

    def warmup(self):
        """起動時に呼ぶ。反射ルールをプリコンパイルする"""
        if self._initialized:
            return
        data = config.get_sync('reflex_rules')
        if data and 'rules' in data:
            for rule in data['rules']:
                try:
                    compiled = re.compile(rule['pattern'])
                    self._compiled_rules.append(
                        (compiled, rule['emotion'], rule['amount'])
                    )
                except re.error:
                    pass  # 不正なパターンはスキップ
        self._initialized = True

    def pick_filler(self, category: str, fatigue: float = 0.0) -> str:
        """
        カテゴリからフィラーを選択する。
        - energyマッチング: fatigueに応じたenergy優先
        - 重複排除: 直近N個は再選択しない
        """
        data = config.get_sync('fillers')
        if not data or category not in data:
            return 'んー……'

        items = data[category]

        # 新旧フォーマット対応（string or dict with energy tag）
        candidates = []
        for item in items:
            if isinstance(item, str):
                candidates.append({'text': item, 'energy': 'mid'})
            elif isinstance(item, dict):
                candidates.append(item)

        if not candidates:
            return 'んー……'

        # 重複排除
        recent = self._recent.get(category, deque(maxlen=self._no_repeat_window))
        available = [c for c in candidates if c['text'] not in recent]
        if not available:
            # 全部使い切った → リセットして全候補から
            recent.clear()
            available = candidates

        # energyマッチング（合うものがあれば優先、なければ全候補から）
        target_energy = _fatigue_to_energy(fatigue)
        matched = [c for c in available if c.get('energy', 'mid') == target_energy]
        pool = matched if matched else available

        # 選択
        chosen = random.choice(pool)
        text = chosen['text']

        # 使用済み記録
        if category not in self._recent:
            self._recent[category] = deque(maxlen=self._no_repeat_window)
        self._recent[category].append(text)

        return text

    def match_reflex(self, text: str) -> list[tuple[str, int]]:
        """
        テキストに対して反射ルールをマッチングする。
        プリコンパイル済みregexを使用（<5ms目標）。

        Returns:
            list of (emotion, amount) tuples
        """
        if not self._initialized:
            self.warmup()

        matches = []
        for compiled_re, emotion, amount in self._compiled_rules:
            if compiled_re.search(text):
                matches.append((emotion, amount))
        return matches


# シングルトン
picker = SmartPicker()
