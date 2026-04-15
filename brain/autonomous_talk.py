# brain/autonomous_talk.py
"""
自律発話エンジン（DMN: Default Mode Network）

配信中に自発的に話し続けるためのメインループ。
外部刺激（コメント）がなくても脳が活動を続ける機構。

設計根拠:
- Raichle et al. (2001): DMN - 外部刺激なし時の自己参照的思考
- 自律発話エンジン設計書（2026-03-23）
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable

from brain.stream_clock import StreamClock, StreamPhase
from brain.topic_engine import TopicEngine, TopicPhase
from shared.smart_picker import picker


@dataclass
class TalkAction:
    """1回の発話アクション"""
    text: str                        # 発話テキスト
    topic: str                       # 話題
    phase: str                       # 話題フェーズ
    heat: int                        # 話題のheat
    source: str                      # "autonomous" or "comment_reaction"
    prompt_hint: str = ""            # LLMに渡したヒント
    transition_type: str = ""        # 転換タイプ（あれば）
    emotion_state: dict = None       # 感情状態（あれば）


# ── フィラー選択はSmartPicker経由 ────────────────────────
# picker.pick_filler(category, fatigue) で重複排除+energyマッチング


class AutonomousTalk:
    """
    自律発話のメインコントローラ。

    使い方:
        talk = AutonomousTalk(clock, topic_engine, generate_fn)
        talk.prepare_topics([...])
        async for action in talk.run():
            # action.text を音声合成に渡す
    """

    def __init__(
        self,
        clock: StreamClock,
        topic_engine: TopicEngine,
        generate_fn: Callable[..., Awaitable[str]],
        min_interval: float = 8.0,    # 最短発話間隔（秒）
        max_interval: float = 15.0,   # 最長沈黙（秒）
    ):
        self.clock = clock
        self.topic_engine = topic_engine
        self.generate_fn = generate_fn  # LLMで発話テキストを生成する関数
        self.min_interval = min_interval
        self.max_interval = max_interval

        # 割込み制御
        self._interrupt_event = asyncio.Event()
        self._interrupt_action: Optional[TalkAction] = None
        self._paused = False

        # closing制御
        self._closing_count = 0
        self._max_closing_speaks = 3
        # opening制御
        self._opening_done = False
        self._opening_stage = 0  # 0=挨拶, 1=確認, 2=完了
        # つぶやき制御
        self._speaks_since_mumble = 0
        # フィラー連続回数（無限ループ防止）
        self._consecutive_fillers = 0

    def prepare_topics(self, topics: list[dict]):
        """
        配信開始時に話題リストを投入する。

        Args:
            topics: [{'topic': str, 'keywords': list, 'source': str, 'priority': int}, ...]
        """
        for t in topics:
            self.topic_engine.add_topic(
                topic=t['topic'],
                keywords=t.get('keywords', []),
                source=t.get('source', 'theme'),
                priority=t.get('priority', 50),
            )

    async def run(self):
        """
        自律発話のメインループ（async generator）。
        配信中、TalkAction を yield し続ける。

        Usage:
            async for action in talk.run():
                await synthesize_voice(action.text)
        """
        while self.clock.is_live:
            # ── 割込みチェック ──
            if self._interrupt_event.is_set():
                self._interrupt_event.clear()
                if self._interrupt_action:
                    yield self._interrupt_action
                    self._interrupt_action = None
                    self.clock.on_speak()
                    continue

            # ── 一時停止中（音声再生中など）──
            if self._paused:
                await asyncio.sleep(0.1)
                continue

            # ── clock tick ──
            clock_state = self.clock.tick()
            phase = StreamPhase(clock_state['phase']) if clock_state['phase'] != 'ended' else StreamPhase.ENDED
            fatigue = clock_state.get('fatigue', 0)

            # ── 沈黙チェック ──
            # min_intervalで判定（heat計算の間隔制御を活かすため）
            if not self.clock.should_speak(self.min_interval):
                await asyncio.sleep(0.5)
                continue

            # ── フェーズ別の特殊発話 ──
            # Opening/Closing の定型発話
            if phase == StreamPhase.OPENING and not self._opening_done:
                if self._opening_stage == 0:
                    text = picker.pick_filler('opening', fatigue)
                    self._opening_stage = 1
                elif self._opening_stage == 1:
                    text = picker.pick_filler('opening_check', fatigue)
                    self._opening_stage = 2
                else:
                    self._opening_done = True
                    continue  # openingフェーズ完了、通常フローへ
                yield TalkAction(
                    text=text, topic='挨拶', phase='opening',
                    heat=0, source='autonomous',
                )
                self.clock.on_speak()
                await asyncio.sleep(2.0)  # opening間はゆっくり
                continue

            if phase == StreamPhase.CLOSING:
                self._closing_count += 1
                if self._closing_count > self._max_closing_speaks:
                    self.clock.stop()
                    break
                text = picker.pick_filler('closing', fatigue)
                yield TalkAction(
                    text=text, topic='締め', phase='closing',
                    heat=0, source='autonomous',
                )
                self.clock.on_speak()
                await asyncio.sleep(self.min_interval)
                continue

            # 疲労が高い時はフィラー（確率を下げた: 30%→15%）
            if fatigue > 70 and self.topic_engine.active_topic:
                import random
                if random.random() < 0.15:
                    text = picker.pick_filler('fatigue', fatigue)
                    yield TalkAction(
                        text=text, topic='フィラー', phase='fatigue',
                        heat=0, source='autonomous',
                    )
                    self.clock.on_speak()
                    await asyncio.sleep(self.min_interval)
                    continue

            # ── topic_engine から次のアクションを取得 ──
            topic_state = self.topic_engine.tick(got_comment=False)

            if topic_state['action'] == 'need_topics':
                self._consecutive_fillers += 1
                if self._consecutive_fillers <= 1:
                    # 1回だけフィラーで場つなぎ（2→1に削減）
                    text = picker.pick_filler('silence_filler', fatigue)
                    yield TalkAction(
                        text=text, topic='場つなぎ', phase='filler',
                        heat=0, source='autonomous',
                    )
                    self.clock.on_speak()
                    await asyncio.sleep(self.min_interval)
                    continue
                else:
                    # 2回目以降：話題なしでもLLMに自由に話させる
                    self._consecutive_fillers = 0
                    topic_state = {
                        'action': 'speak',
                        'topic': '雑談',
                        'phase': 'DEVELOP',
                        'heat': 40,
                        'prompt_hint': '話題が尽きた。新しい話題を自分で見つけて話す。'
                                       '「てかさ、」「あのさ、」で自然に切り出す。',
                    }
                    # ↓ LLM生成に落ちる（continueしない）

            # ── 話題転換時の「考え中」（低確率・1回だけ → さらに下げ: 30%→15%）──
            import random
            if topic_state['phase'] == 'INTRO' and topic_state.get('total_turns', 0) == 0:
                if random.random() < 0.15:
                    text = picker.pick_filler('thinking', fatigue)
                    yield TalkAction(
                        text=text, topic='考え中', phase='thinking',
                        heat=0, source='autonomous',
                    )
                    self.clock.on_speak()
                    await asyncio.sleep(1.5)

            # ── ランダムつぶやき（12発話に1回くらい・低確率に下げ）──
            self._speaks_since_mumble += 1
            if self._speaks_since_mumble >= 12 and random.random() < 0.12:
                self._speaks_since_mumble = 0
                text = picker.pick_filler('mumble', fatigue)
                yield TalkAction(
                    text=text, topic='つぶやき', phase='mumble',
                    heat=0, source='autonomous',
                )
                self.clock.on_speak()
                await asyncio.sleep(1.0)

            # ── チャット確認（コメント3分以上なし・さらに低確率に）──
            if (self.clock.comment_silence_seconds > 180
                    and random.random() < 0.05):
                text = picker.pick_filler('check_chat', fatigue)
                yield TalkAction(
                    text=text, topic='チャット確認', phase='filler',
                    heat=0, source='autonomous',
                )
                self.clock.on_speak()
                await asyncio.sleep(2.0)

            # ── LLMで発話テキスト生成 ──
            try:
                text = await self.generate_fn(
                    prompt_hint=topic_state['prompt_hint'],
                    topic=topic_state['topic'],
                    phase=topic_state['phase'],
                    heat=topic_state['heat'],
                )
            except Exception as e:
                # LLMエラー時はフィラーで場つなぎ
                text = picker.pick_filler('silence_filler', fatigue)

            action = TalkAction(
                text=text,
                topic=topic_state['topic'],
                phase=topic_state['phase'],
                heat=topic_state['heat'],
                source='autonomous',
                prompt_hint=topic_state['prompt_hint'],
                transition_type=topic_state.get('transition_type', ''),
            )

            # 正常な発話が出たらフィラーカウンターをリセット
            self._consecutive_fillers = 0

            yield action
            self.clock.on_speak()

            # ── 次の発話まで待機 ──
            # 音声再生が既に間を作っているので、追加waitは最小限
            # （コメント割込みの処理余地として0.5秒だけ待つ）
            await asyncio.sleep(0.5)

    # ── 外部からの割込みAPI ──

    def inject_interrupt(self, action: TalkAction):
        """コメント反応などの割込みを注入する"""
        self._interrupt_action = action
        self._interrupt_event.set()

    def pause(self):
        """一時停止（音声再生中など）"""
        self._paused = True

    def resume(self):
        """再開"""
        self._paused = False
