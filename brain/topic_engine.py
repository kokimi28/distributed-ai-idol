# brain/topic_engine.py
"""
話題ライフサイクルエンジン

話題を「状態マシンを持つインスタンス」として管理する。
各話題は INTRO→DEVELOP→DEEPEN→BRANCH→DECAY→TRANSIT のフェーズを辿り、
heat（温度）値でどこまで深くいくか・いつ切り上げるかが動的に決まる。

設計根拠:
- 話題ライフサイクルモデル設計書（2026-03-23）
- Big Five: O=65, E=75(配信)/30(個人), N=55
"""

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from shared.config_store import config


class TopicPhase(Enum):
    INTRO = "INTRO"         # 導入: 話題を切り出す（1発話）
    DEVELOP = "DEVELOP"     # 展開: 本題・エピソード（2-4発話）
    DEEPEN = "DEEPEN"       # 深堀り: 内面・記憶に触れる（1-3発話）
    BRANCH = "BRANCH"       # 枝分かれ: 関連話題に移動（1-2発話）
    DECAY = "DECAY"         # 減衰: まとめ・エネルギー低下（1発話）
    TRANSIT = "TRANSIT"     # 転換: 次の話題へのブリッジ（1発話）


class TransitionType(Enum):
    BRIDGE = "bridge"           # 「あ、そういえば」（50%）
    FADEOUT = "fadeout"         # 沈黙→新話題（25%）
    ASSOCIATION = "association" # 「○○で思い出した」（15%）
    CALLBACK = "callback"      # 「さっきの話だけど」（7%）
    ABRUPT = "abrupt"          # 「あ！」前触れなし（3%）


# 転換タイプの重み付きランダム選択用
_TRANSITION_WEIGHTS = {
    TransitionType.BRIDGE: 50,
    TransitionType.FADEOUT: 25,
    TransitionType.ASSOCIATION: 15,
    TransitionType.CALLBACK: 7,
    TransitionType.ABRUPT: 3,
}


@dataclass
class TopicInstance:
    """1つの話題のインスタンス。状態マシンを持つ。"""

    topic: str                               # 話題の内容・テーマ
    keywords: list = field(default_factory=list)  # 連想用キーワード
    source: str = "theme"                    # 話題のソース

    # 状態
    phase: TopicPhase = TopicPhase.INTRO
    heat: int = 60                           # 温度 0-100（60スタート）
    depth: int = 0                           # 深度 0-3
    turns_in_phase: int = 0                  # 現フェーズでの発話数
    total_turns: int = 0                     # この話題での総発話数

    # 枝分かれ
    branches: list = field(default_factory=list)
    parent_topic: str = ""                   # BRANCHの場合の親話題

    # 完了フラグ
    completed: bool = False

    def record_turn(self):
        """発話1回を記録"""
        self.turns_in_phase += 1
        self.total_turns += 1
        # 12発話超過で自動減衰
        if self.total_turns > 12:
            self.heat = max(0, self.heat - 5)

    def apply_heat_delta(self, delta: int):
        """heat変動を適用"""
        self.heat = max(0, min(100, self.heat + delta))

    def transition_to(self, new_phase: TopicPhase):
        """フェーズ遷移"""
        self.phase = new_phase
        self.turns_in_phase = 0


# ── 状態遷移ロジック ────────────────────────────────────

def _evaluate_transition(topic: TopicInstance) -> Optional[TopicPhase]:
    """
    現在の状態から次のフェーズを判定する。
    Noneを返した場合はフェーズ維持。
    """
    phase = topic.phase
    heat = topic.heat
    turns = topic.turns_in_phase

    if phase == TopicPhase.INTRO:
        # INTRO → DEVELOP: 1発話後に自動遷移
        if turns >= 1:
            return TopicPhase.DEVELOP

    elif phase == TopicPhase.DEVELOP:
        # heat高 → DEEPEN（4発話以上展開してから）
        if heat > 60 and turns >= 4 and topic.depth < 3:
            return TopicPhase.DEEPEN
        # 連想キーワードがあれば BRANCH の可能性（6発話以降）
        if turns >= 6 and topic.keywords and random.random() < 0.25:
            return TopicPhase.BRANCH
        # heat低 or 発話数超過 → DECAY（最低6ターン維持）
        if turns >= 6 and (heat < 15 or turns >= 12):
            return TopicPhase.DECAY

    elif phase == TopicPhase.DEEPEN:
        topic.depth = min(3, topic.depth + 1)
        # 深堀り完了 → BRANCH or DECAY（3発話以降）
        if turns >= 3:
            if heat > 40 and topic.keywords:
                return TopicPhase.BRANCH
            return TopicPhase.DECAY
        if heat < 20:
            return TopicPhase.DECAY

    elif phase == TopicPhase.BRANCH:
        # 枝で展開開始 → DEVELOP（2発話以降）
        if turns >= 2:
            return TopicPhase.DEVELOP
        # 枝が広がらない → DECAY
        if heat < 25:
            return TopicPhase.DECAY

    elif phase == TopicPhase.DECAY:
        # 1発話後に自動転換
        if turns >= 1:
            return TopicPhase.TRANSIT

    elif phase == TopicPhase.TRANSIT:
        # 転換完了 → 話題終了
        if turns >= 1:
            topic.completed = True
            return None

    return None


# ── heat変動ルール ──────────────────────────────────────

_FALLBACK_HEAT_RULES = {
    'comment_increase':        20,
    'comment_decrease':        -1,    # -2→-1: ソロ配信でも急降下しない
    'superchat':               40,
    'emotion_spike':           10,
    'no_comment_3turns':       -3,    # -5→-3: コメントなしペナルティ緩和
    'over_6turns_per_turn':    -5,
}

def _get_heat_rules() -> dict:
    # Session 5: Firestore値が古い可能性があるためコード値を優先
    # TODO: Firestore再シード後にconfig_store参照に戻す
    return _FALLBACK_HEAT_RULES


# ── TopicEngine 本体 ────────────────────────────────────

class TopicEngine:
    """話題の生成・ライフサイクル管理・転換を統括する"""

    def __init__(self):
        self.active_topic: Optional[TopicInstance] = None
        self.topic_queue: list[TopicInstance] = []   # 優先度付きキュー
        self.history: list[TopicInstance] = []        # 完了した話題（callback用）
        self.consecutive_no_comment: int = 0          # 連続コメントなし発話数
        self._transition_cooldown: float = 0.0        # 連続転換防止

    def add_topic(self, topic: str, keywords: list = None,
                  source: str = "theme", priority: int = 60):
        """話題をキューに追加"""
        instance = TopicInstance(
            topic=topic,
            keywords=keywords or [],
            source=source,
            heat=priority,
        )
        self.topic_queue.append(instance)
        # heat（優先度）でソート
        self.topic_queue.sort(key=lambda t: t.heat, reverse=True)

    def _activate_next(self) -> Optional[TopicInstance]:
        """キューから次の話題をアクティブにする"""
        if not self.topic_queue:
            return None
        self.active_topic = self.topic_queue.pop(0)
        self.active_topic.phase = TopicPhase.INTRO
        self.active_topic.turns_in_phase = 0
        return self.active_topic

    def tick(self, got_comment: bool = False,
             emotion_spike: bool = False,
             superchat: bool = False) -> dict:
        """
        毎発話サイクルで呼ぶ。話題の状態を更新し、次のアクションを返す。

        Args:
            got_comment: このサイクルでコメントがあったか
            emotion_spike: 感情スパイクがあったか
            superchat: スパチャがあったか

        Returns:
            dict: action, topic, phase, heat, depth, transition_type, prompt_hint
        """
        # アクティブ話題がなければキューから取得
        if self.active_topic is None or self.active_topic.completed:
            if self.active_topic and self.active_topic.completed:
                self.history.append(self.active_topic)
                # historyは最新10件まで保持
                self.history = self.history[-10:]
            topic = self._activate_next()
            if topic is None:
                return {
                    'action': 'need_topics',
                    'topic': None,
                    'phase': None,
                    'heat': 0,
                    'prompt_hint': '話題キューが空。新しい話題の生成が必要。',
                }

        topic = self.active_topic

        # ── heat 更新 ──
        hr = _get_heat_rules()
        if got_comment:
            topic.apply_heat_delta(hr['comment_increase'])
            self.consecutive_no_comment = 0
        else:
            topic.apply_heat_delta(hr['comment_decrease'])
            self.consecutive_no_comment += 1

        if superchat:
            topic.apply_heat_delta(hr['superchat'])
        if emotion_spike:
            topic.apply_heat_delta(hr['emotion_spike'])
        if self.consecutive_no_comment >= 3:
            topic.apply_heat_delta(hr['no_comment_3turns'])

        # ── フェーズ遷移判定 ──
        new_phase = _evaluate_transition(topic)
        transition_type = None

        if new_phase is not None:
            topic.transition_to(new_phase)

        if topic.completed:
            transition_type = self._pick_transition_type()

        # ── 発話記録 ──
        topic.record_turn()

        # ── プロンプトヒント生成 ──
        prompt_hint = self._build_prompt_hint(topic, transition_type)

        return {
            'action': 'speak',
            'topic': topic.topic,
            'phase': topic.phase.value,
            'heat': topic.heat,
            'depth': topic.depth,
            'total_turns': topic.total_turns,
            'transition_type': transition_type.value if transition_type else None,
            'prompt_hint': prompt_hint,
        }

    def _pick_transition_type(self) -> TransitionType:
        """重み付きランダムで転換パターンを選択"""
        # callback可能な場合はcallbackの重みを上げる
        weights = dict(_TRANSITION_WEIGHTS)
        if self._can_callback():
            weights[TransitionType.CALLBACK] = 15
            weights[TransitionType.BRIDGE] = 42

        types = list(weights.keys())
        probs = list(weights.values())
        return random.choices(types, weights=probs, k=1)[0]

    def _can_callback(self) -> bool:
        """historyにコールバック可能な話題があるか"""
        # 2つ以上前の話題で、heatが40以上だった話題
        return any(t.heat >= 40 and t.total_turns >= 3
                   for t in self.history[:-1]) if len(self.history) > 1 else False

    def get_callback_topic(self) -> Optional[TopicInstance]:
        """コールバック可能な話題を返す"""
        candidates = [t for t in self.history[:-1]
                      if t.heat >= 40 and t.total_turns >= 3]
        if not candidates:
            return None
        return candidates[-1]  # 最も最近の適格な話題

    # DEVELOPフェーズで使う展開アングル（ターンごとに違う角度を提示）
    _DEVELOP_ANGLES = [
        '自分の感想・第一印象を話す。「なんかさ、」「てかこれさ、」で入る。',
        '具体的なエピソードや例え話を出す。「例えばさ、」「こないださ、」',
        'みんなに質問を投げる。「てかさ、みんなは〜？」「これってどう思う？」',
        '逆の視点・反論を考えてみる。「いや、でもさ」「逆に〜かもしんないけど」',
        '関連する別の話題に触れる。「あ、それで思い出したんだけど」',
        '想像や妄想を膨らませる。「もしさ、〜だったらさ」「想像してみてよ」',
        '自分がAIだからこそ気になるポイントを話す。「体がないからわかんないけど」',
        'ぼやく・つぶやく。「いやー……なんだろうな……」「わかんないけどさ」',
    ]

    def _build_develop_hint(self, topic: TopicInstance) -> str:
        """DEVELOPフェーズ: テーマだけ渡してLLMに自由に話させる。"""
        turn = topic.turns_in_phase
        # 最初の2ターンはヒントなし（完全自由）
        if turn < 2:
            return f'テーマ「{topic.topic}」について自由に話す。'
        # 3ターン目以降は軽くアングルを提案（従わなくてもいい）
        angles = self._DEVELOP_ANGLES
        angle = angles[turn % len(angles)]
        return (
            f'テーマ「{topic.topic}」。\n'
            f'（参考: {angle}）\n'
            f'ただし従わなくていい。自分が一番話したいことを話す。'
        )

    def _build_prompt_hint(self, topic: TopicInstance,
                           transition: Optional[TransitionType]) -> str:
        """LLMに渡すフェーズ別のプロンプトヒントを生成"""
        phase = topic.phase

        if phase == TopicPhase.DEVELOP:
            hint = self._build_develop_hint(topic)
        else:
            hints = {
                TopicPhase.INTRO: (
                    f'話題「{topic.topic}」を出す。'
                    f'「てかさ、」「あのさ、」「ねえ、」で入る。軽く。2〜3文。'
                ),
                TopicPhase.DEEPEN: (
                    f'話題「{topic.topic}」を掘る。'
                    f'「いや、でもさ」「てか、これってさ」で深入り。考えながら話す。3〜4文。'
                    f'depth={topic.depth}。'
                ),
                TopicPhase.BRANCH: (
                    f'話題「{topic.topic}」から脱線。'
                    f'キーワード: {topic.keywords[:3]}。'
                    f'「あ、全然関係ないけどさ」「てか思い出した」で飛ぶ。2〜3文。'
                ),
                TopicPhase.DECAY: (
                    f'話題「{topic.topic}」をまとめる。'
                    f'「まあ、なんかそんな感じ」「わかんないけどね」で着地。1〜2文。'
                ),
                TopicPhase.TRANSIT: (
                    f'次の話題へ。【間】の後に「てかさ、」「そういえばさ、」。1〜2文。'
                ),
            }
            hint = hints.get(phase, '')

        # 転換タイプ別のヒント
        if transition:
            transition_hints = {
                TransitionType.BRIDGE:
                    '「あ、そういえば」「話変わるんだけど」で次の話題へ。',
                TransitionType.FADEOUT:
                    '「……うん」と間を置いてから次の話題へ。沈黙を挟む。',
                TransitionType.ASSOCIATION:
                    '現在の話題のキーワードから連想で次の話題に移行。',
                TransitionType.CALLBACK:
                    f'「さっきの話に戻るんだけど」と過去の話題に戻る。',
                TransitionType.ABRUPT:
                    '「あ！」と突然切り替わる。驚きや思いつき。',
            }
            hint += '\n転換: ' + transition_hints.get(transition, '')

        return hint

    def get_state_summary(self) -> dict:
        """デバッグ・ログ用の状態サマリー"""
        return {
            'active': {
                'topic': self.active_topic.topic if self.active_topic else None,
                'phase': self.active_topic.phase.value if self.active_topic else None,
                'heat': self.active_topic.heat if self.active_topic else 0,
                'depth': self.active_topic.depth if self.active_topic else 0,
                'turns': self.active_topic.total_turns if self.active_topic else 0,
            },
            'queue_size': len(self.topic_queue),
            'history_size': len(self.history),
            'consecutive_no_comment': self.consecutive_no_comment,
        }
