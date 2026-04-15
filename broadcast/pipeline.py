# broadcast/pipeline.py
"""
配信パイプライン統合

全Stageをイベントループ型で統合する。
- メインループ: autonomous_talk（自律発話・DMN）
- イベント割込み: コメント反応（reflex → blender → LLM）
- 出力: voice(synthesizer) + vtube(表情制御) + memory(Zep)
- コメント取得: YouTube Live Chat API ポーリング（★追加）

アーキテクチャ:
  ┌─ 自律発話ループ（常時稼働）
  │  stream_clock → topic_engine → autonomous_talk → LLM → voice → vtube
  ├─ コメント割込み（イベント駆動）
  │  comment → reflex_layer → comment_blender → LLM → voice → vtube
  ├─ YouTube Chatポーリング（★追加）
  │  YouTube Live Chat API → ChatComment → on_comment() → コメント割込み
  └─ 記憶保存（非同期バックグラウンド）
"""

import asyncio
import json
import os
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

from dotenv import load_dotenv
from loguru import logger

from brain.stream_clock import StreamClock, StreamPhase
from brain.topic_engine import TopicEngine
from brain.autonomous_talk import AutonomousTalk, TalkAction
from brain.reflex_layer import apply_reflex, merge_spike_to_state, EmotionSpike
from character.emotion_to_voice import convert_emotion_to_voice
from voice.synthesizer import VoicePipeline, VoiceSettings, SynthResult
from broadcast.youtube_chat import YouTubeChatPoller, ChatComment  # ★追加
from voice.text_parser import parse_speech_text  # Phase2
from memory.zep_client import ZepMemory  # ★Phase8追加
from broadcast.overlay_server import OverlayServer  # ★ビジュアルオーバーレイ
from video.video_generator import VideoGenerator  # ★AI動画生成
from video.image_generator import ImageGenerator  # ★AI画像生成
from video.clip_selector import ClipSelector  # ★ライブクリップ選択

load_dotenv()


@dataclass
class PipelineConfig:
    """パイプラインの設定"""
    # 配信
    planned_duration_minutes: float = 60.0
    # 音声
    prefer_voice_engine: str = "aivispeech"
    # 自律発話
    min_speak_interval: float = 0.5
    max_silence: float = 3.0
    # モード
    mode: str = "broadcast"        # "broadcast" or "private"
    # VTube Studio
    vtube_host: str = "localhost"
    vtube_port: int = 8001
    enable_vtube: bool = True
    # 話題
    initial_topics: list = field(default_factory=list)
    # YouTube Chat  ★追加
    enable_youtube_chat: bool = True
    youtube_live_chat_id: Optional[str] = None  # 自動検出しない場合に直接指定
    # ビジュアルオーバーレイ  ★追加
    enable_overlay: bool = True
    overlay_port: int = 8765


class BroadcastPipeline:
    """
    配信パイプラインのメインコントローラ。

    Usage:
        config = PipelineConfig(initial_topics=[...])
        pipeline = BroadcastPipeline(config, llm_generate_fn)
        await pipeline.start()
        # コメントが来たら:
        await pipeline.on_comment("こんばんは！", user_id="user123")
        # 配信終了:
        await pipeline.stop()
    """

    def __init__(self, config: PipelineConfig,
                 llm_generate_fn: Callable[..., Awaitable[str]]):
        self.config = config
        self.llm_generate = llm_generate_fn

        # コンポーネント初期化
        self.clock = StreamClock(
            planned_duration_minutes=config.planned_duration_minutes
        )
        self.topic_engine = TopicEngine()
        self.voice = VoicePipeline(prefer_engine=config.prefer_voice_engine)

        # VTube Studio（遅延初期化）
        self._vtube = None

        # autonomous_talk
        self._talk = AutonomousTalk(
            clock=self.clock,
            topic_engine=self.topic_engine,
            generate_fn=self._generate_for_autonomous,
            min_interval=config.min_speak_interval,
            max_interval=config.max_silence,
        )

        # 感情状態
        self.char_state = {
            'joy': 40, 'sadness': 0, 'anger': 0, 'surprise': 0,
            'embarrass': 0, 'fear': 0, 'affection': 50,
            'fatigue': 0, 'tension': 40, 'loneliness': 0,
        }

        # コメントキュー（割込み待ち行列）
        self._comment_queue: asyncio.Queue = asyncio.Queue()

        # 未処理コメントバッファ（自律発話に統合する用）
        self._pending_comments: list[dict] = []

        # タスク管理
        self._main_task: Optional[asyncio.Task] = None
        self._comment_task: Optional[asyncio.Task] = None
        self._speaker_task: Optional[asyncio.Task] = None

        # Prefetchバッファ（1個だけ先読み。溜めすぎると間がなくなる）
        self._speak_queue: asyncio.Queue = asyncio.Queue(maxsize=1)

        # コールバック（外部連携用）
        self.on_speak_callback: Optional[Callable] = None
        self.on_expression_callback: Optional[Callable] = None

        # 状態
        self._is_running = False
        self._recent_comments: list[str] = []
        self._last_overlay_topic: str = ''  # 話題切り替え検知用

        # YouTube Chat  ★追加
        self._youtube_poller: Optional[YouTubeChatPoller] = None
        self._youtube_task: Optional[asyncio.Task] = None

        # Zep記憶レイヤー  ★Phase8追加
        self._zep = ZepMemory()

        # ビジュアルオーバーレイ  ★追加
        self._overlay = OverlayServer(port=config.overlay_port)

        # AI動画生成  ★追加
        self._video_gen = VideoGenerator(
            overlay_server=self._overlay,
            provider=os.getenv('KLING_PROVIDER', 'piapi'),
            api_key=os.getenv('KLING_API_KEY', ''),
        )

        # AI画像生成  ★追加
        self._image_gen = ImageGenerator(
            overlay_server=self._overlay,
            api_key=os.getenv('KLING_API_KEY', ''),
        )

        # ★ライブクリップ選択（プリレンダー済みクリップから状況に応じて選択）
        self._clip_selector = ClipSelector(overlay_server=self._overlay)
        self._clip_timer_task: Optional[asyncio.Task] = None

    # ── ライフサイクル ──────────────────────────────────

    async def start(self):
        """配信パイプラインを開始する"""
        # 音声エンジン初期化
        try:
            engine_name = await self.voice.initialize()
        except RuntimeError:
            engine_name = "(none - dry run)"

        # VTube Studio接続（オプション）
        if self.config.enable_vtube:
            try:
                from broadcast.vtube_control import VTubeController
                self._vtube = VTubeController(
                    host=self.config.vtube_host,
                    port=self.config.vtube_port,
                )
                await self._vtube.connect()
            except Exception:
                self._vtube = None

        # 話題投入
        if self.config.initial_topics:
            self._talk.prepare_topics(self.config.initial_topics)

        # 配信開始
        self.clock.start()
        self._is_running = True

        # メインループ・コメントワーカー・スピーカーを起動
        self._main_task = asyncio.create_task(self._autonomous_loop())
        def _on_task_done(t):
            try:
                exc = t.exception()
                if exc:
                    import sys
                    print(f'[AUTONOMOUS CRASH] {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
                    import traceback
                    traceback.print_exception(exc)
            except asyncio.CancelledError:
                pass
        self._main_task.add_done_callback(_on_task_done)
        self._comment_task = asyncio.create_task(self._comment_worker())
        self._speaker_task = asyncio.create_task(self._speaker_worker())

        # YouTube Chatポーリング開始  ★追加
        youtube_chat_active = False
        if self.config.enable_youtube_chat:
            self._youtube_poller = YouTubeChatPoller(
                on_comment=self._on_youtube_comment,
                channel_id=os.getenv('YOUTUBE_CHANNEL_ID'),
            )
            started = await self._youtube_poller.start(
                live_chat_id=self.config.youtube_live_chat_id
            )
            if started:
                self._youtube_task = asyncio.create_task(
                    self._youtube_poller.poll_loop()
                )
                youtube_chat_active = True

        # Zep記憶レイヤー初期化  ★Phase8追加
        zep_active = await self._zep.initialize()
        if zep_active:
            session_label = datetime.now().strftime("%Y%m%d_%H%M%S")
            await self._zep.start_session(session_label)

        # ビジュアルオーバーレイ起動  ★追加
        overlay_active = False
        if self.config.enable_overlay:
            overlay_active = await self._overlay.start()

        # ★クリップ自動切替タイマー（10-15秒ごと）
        if self._clip_selector.has_clips:
            self._clip_timer_task = asyncio.create_task(self._clip_timer_loop())

        return {
            'status': 'started',
            'voice_engine': engine_name,
            'vtube_connected': self._vtube is not None and self._vtube.is_connected,
            'topics_loaded': len(self.topic_engine.topic_queue),
            'youtube_chat': youtube_chat_active,  # ★追加
            'zep_memory': zep_active,  # ★Phase8追加
            'overlay': overlay_active,  # ★ビジュアルオーバーレイ
            'video_gen': self._video_gen.is_enabled,  # ★AI動画
        }

    async def stop(self):
        """配信パイプラインを停止する"""
        self._is_running = False
        self.clock.stop()

        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass

        if self._comment_task:
            self._comment_task.cancel()
            try:
                await self._comment_task
            except asyncio.CancelledError:
                pass

        if self._speaker_task:
            self._speaker_task.cancel()
            try:
                await self._speaker_task
            except asyncio.CancelledError:
                pass

        # YouTube Chat停止  ★追加
        if self._youtube_poller:
            self._youtube_poller.stop()
        if self._youtube_task:
            self._youtube_task.cancel()
            try:
                await self._youtube_task
            except asyncio.CancelledError:
                pass
        # ★クリップタイマー停止
        if self._clip_timer_task:
            self._clip_timer_task.cancel()
            try:
                await self._clip_timer_task
            except asyncio.CancelledError:
                pass
                await self._youtube_task
            except asyncio.CancelledError:
                pass

        if self._vtube:
            await self._vtube.disconnect()

        self.voice.close()

        # Zepセッション終了（感情スナップショット保存）★Phase8追加
        if self._zep.is_enabled:
            await self._zep.end_session(emotion_snapshot=dict(self.char_state))

        # ビジュアルオーバーレイ停止  ★追加
        if self._overlay.is_running:
            await self._overlay.stop()

        return {
            'status': 'stopped',
            'total_speaks': self.clock._total_speaks,
            'final_emotions': dict(self.char_state),
        }

    # ── 外部API ────────────────────────────────────────

    async def on_comment(self, text: str, user_id: str = "",
                         is_superchat: bool = False,
                         is_mention: bool = False):
        """
        コメント受信時に呼ぶ。
        コメントキューに積み、comment_workerが処理する。
        """
        await self._comment_queue.put({
            'text': text,
            'user_id': user_id,
            'is_superchat': is_superchat,
            'is_mention': is_mention,
            'timestamp': time.time(),
        })
        self.clock.on_comment()

    def add_topics(self, topics: list[dict]):
        """配信中に話題を追加する"""
        self._talk.prepare_topics(topics)

    # ── メインループ（自律発話）───────────────────────

    async def _autonomous_loop(self):
        """autonomous_talkからの発話を準備し、speak_queueに先読みする"""
        logger.info('[autonomous] loop started')
        try:
            async for action in self._talk.run():
                logger.info(f'[autonomous] got action: {action.text[:40] if action.text else "empty"}')
                if not self._is_running:
                    break
                try:
                    prepared = await self._prepare_action(action)
                    if prepared:
                        await self._speak_queue.put(prepared)
                    else:
                        logger.warning(f'[autonomous] prepare returned None for: {action.text[:30]}')
                except Exception as e:
                    logger.error(f'[autonomous] prepare failed: {e}')
                    import traceback
                    traceback.print_exc()
            logger.info('[autonomous] loop ended (generator exhausted)')
        except asyncio.CancelledError:
            logger.info('[autonomous] loop cancelled')
        except Exception as e:
            logger.error(f'[autonomous] loop crashed: {e}')
            import traceback
            traceback.print_exc()
            traceback.print_exc()

    # ── コメントワーカー ────────────────────────────────

    async def _comment_worker(self):
        """コメントを収集し、反射層を通してバッファに蓄積する"""
        try:
            while self._is_running:
                try:
                    comment = await asyncio.wait_for(
                        self._comment_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # 反射層だけ即時実行（感情状態への反映）
                text = comment['text']
                spike = apply_reflex(text)
                self.char_state = merge_spike_to_state(self.char_state, spike)

                # ★クリップセレクター: コメント → reaction クリップに切替
                if self._clip_selector.has_clips:
                    self._clip_selector.on_comment(spike)

                # Zepにユーザーメッセージを保存  ★Phase8追加
                if self._zep.is_enabled:
                    asyncio.create_task(self._zep.save_user_message(
                        user_id=comment.get('user_id', 'anonymous'),
                        display_name=comment.get('user_id', 'anonymous'),
                        text=text,
                        is_superchat=comment.get('is_superchat', False),
                    ))

                # topic_engineにコメント通知
                self.topic_engine.tick(got_comment=True)

                # ビジュアルオーバーレイにコメントイベント配信  ★追加
                if self._overlay.is_running:
                    # 反射スパイクの最大値を特定
                    spike_type = ''
                    spike_amount = 0
                    for attr in ['surprise', 'defensiveness', 'warmth',
                                 'attention', 'joy_reflex', 'fear_reflex']:
                        val = getattr(spike, attr, 0)
                        if val > spike_amount:
                            spike_amount = val
                            spike_type = attr
                    self._overlay.broadcast_comment(
                        text=text,
                        user_id=comment.get('user_id', ''),
                        spike_type=spike_type,
                        spike_amount=spike_amount,
                        is_superchat=comment.get('is_superchat', False),
                    )

                # 未処理バッファに追加（次の自律発話で使う）
                self._pending_comments.append(comment)
                # 最大5件まで保持（古いのは落とす）
                if len(self._pending_comments) > 5:
                    self._pending_comments = self._pending_comments[-5:]

                self._recent_comments.append(text)
                self._recent_comments = self._recent_comments[-20:]
        except asyncio.CancelledError:
            pass

    # ── Prefetchパイプライン ──────────────────────────────

    async def _prepare_action(self, action: TalkAction):
        """TalkActionをセグメント分割し、各セグメントの音声を合成する"""
        if not action.text or not action.text.strip():
            return None

        # テキストをセグメントに分割（フィラーはインライン、間だけ分割）
        segments = parse_speech_text(action.text)
        if not segments:
            return None

        # 感情→音声パラメータ
        voice_params = convert_emotion_to_voice(
            self.char_state, self.config.mode
        )
        settings = VoiceSettings(
            stability=voice_params['stability'],
            similarity_boost=voice_params['similarity_boost'],
            style=voice_params['style'],
            use_speaker_boost=voice_params.get('use_speaker_boost', True),
        )

        # 感情→表情
        expression = None
        if self._vtube and self._vtube.is_connected:
            try:
                from broadcast.vtube_control import emotion_to_expression
                expression = emotion_to_expression(
                    self.char_state, self.config.mode
                )
            except Exception:
                pass

        # 各セグメントの音声を合成（同一設定で統一）
        prepared_segments = []
        for seg in segments:
            if seg.type == "silence":
                prepared_segments.append(('silence', seg.duration_ms, None))
            else:  # speech（フィラーもインライン済み）
                try:
                    result = await self.voice.speak(
                        seg.text, voice_settings=settings,
                        play_audio=False
                    )
                    prepared_segments.append(('audio', 0, result))
                except Exception:
                    pass

        if not prepared_segments:
            return None

        return (action, prepared_segments, expression)

    async def _speaker_worker(self):
        """speak_queueから取り出して再生する（1つずつ順番に）"""
        # AudioPlayerを事前初期化
        from voice.synthesizer import AudioPlayer
        if self.voice.player is None:
            self.voice.player = AudioPlayer()
            self.voice.player._find_device()

        try:
            while self._is_running:
                try:
                    prepared = await asyncio.wait_for(
                        self._speak_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                try:
                    await self._play_prepared(prepared)
                except Exception as e:
                    logger.error(f'[speaker] play failed: {e}')
                    import traceback
                    traceback.print_exc()
                # 発話間の「生きてる沈黙」（文脈で変わる）
                pause = self._calc_breath_pause(prepared)
                await asyncio.sleep(pause)
                # ★沈黙中 → activity クリップに切替
                if self._clip_selector.has_clips:
                    action = prepared[0]
                    topic_key = self._find_topic_key(
                        action.topic if action else '')
                    self._clip_selector.on_silence(topic_key)
        except asyncio.CancelledError:
            pass

    def _calc_breath_pause(self, prepared) -> float:
        """発話後の沈黙を計算。状況に応じて変わる。"""
        import random
        action = prepared[0]
        text = action.text if action else ''
        phase = action.phase if action else ''

        # コメントの活発さを見る
        comment_silence = self.clock.comment_silence_seconds if self.clock.is_live else 0
        lonely = comment_silence > 120  # 2分以上コメントなし

        # 質問した後 → コメント待ち（長め）
        if '？' in text or '?' in text:
            return random.uniform(4.0, 7.0) if lonely else random.uniform(3.0, 5.0)

        # 話題の締め・転換前
        if phase in ('DECAY', 'TRANSIT', 'closing'):
            return random.uniform(3.0, 5.0) if lonely else random.uniform(2.0, 3.5)

        # opening
        if phase == 'opening':
            return random.uniform(1.0, 2.0)

        # コメントなし状態 → ゆっくりめ（ぼそぼそ感）
        if lonely:
            return random.uniform(2.5, 5.0)

        # 通常
        return random.uniform(1.0, 3.0)

    async def _play_prepared(self, prepared):
        """準備済みセグメントを順番に再生する"""
        action, prepared_segments, expression = prepared

        # ★字幕を再生開始前に即送信（遅延解消）
        if self._overlay.is_running and action:
            self._overlay.broadcast_subtitle(
                text=action.text,
                topic=action.topic,
                phase=action.phase,
            )
            # ★クリップセレクター: 発話中 → talking クリップに切替
            if self._clip_selector.has_clips:
                topic_key = self._find_topic_key(action.topic)
                self._clip_selector.on_speak(topic_key)

            # ★感情状態をオーロラにブロードキャスト（雰囲気連動）
            self._overlay._broadcast({
                'type': 'state_update',
                'emotions': dict(self.char_state),
            })

        # 表情制御（バックグラウンドで連続注入）
        expression_task = None
        if expression and self._vtube and self._vtube.is_connected:
            try:
                expression_task = asyncio.create_task(
                    self._vtube.hold_expression(expression, duration=30.0)
                )
            except Exception:
                pass

        # セグメントを順番に再生
        loop = asyncio.get_event_loop()
        short_pause_count = 0
        did_cut = False
        seg_summary = [(s[0], s[1]) for s in prepared_segments]
        logger.info(f'[segments] {seg_summary}')
        for seg_type, duration_ms, result in prepared_segments:
            if seg_type == 'silence':
                is_long = duration_ms >= 1200  # 【長間】
                if not is_long:
                    short_pause_count += 1
                # ★【長間】の時だけカットアウェイ（短い間では切り替えない）
                if not did_cut and is_long and self._clip_selector.has_clips:
                    if self._clip_selector.send_cutaway():
                        did_cut = True
                await asyncio.sleep(duration_ms / 1000.0)
            elif seg_type == 'audio' and result:
                try:
                    if result.format == "wav" and self.voice.player:
                        await loop.run_in_executor(
                            None, self.voice.player.play_wav,
                            result.audio_data
                        )
                except Exception:
                    pass

        # 表情タスク停止
        if expression_task and not expression_task.done():
            expression_task.cancel()
            try:
                await expression_task
            except asyncio.CancelledError:
                pass

        # 疲労蓄積
        self.char_state['fatigue'] = min(
            100, self.char_state.get('fatigue', 0) + 1
        )

        # ZepにAI応答を保存  ★Phase8追加
        if self._zep.is_enabled and action and action.text:
            asyncio.create_task(self._zep.save_assistant_message(action.text))

        # 話題のheat/phaseから感情を自動変動させる（心理学的改善）
        if action.heat > 60:
            self.char_state['joy'] = min(100, self.char_state.get('joy', 0) + 3)
            self.char_state['tension'] = max(0, self.char_state.get('tension', 0) - 2)
        elif action.heat < 30:
            self.char_state['joy'] = max(10, self.char_state.get('joy', 0) - 1)
            self.char_state['loneliness'] = min(60, self.char_state.get('loneliness', 0) + 1)
        if action.phase in ('DEEPEN',):
            self.char_state['tension'] = min(100, self.char_state.get('tension', 0) + 3)
        if action.phase in ('DECAY', 'closing'):
            self.char_state['tension'] = max(10, self.char_state.get('tension', 0) - 3)

        # コールバック
        if self.on_speak_callback:
            try:
                self.on_speak_callback(action, None)
            except Exception:
                pass

        # ビジュアルオーバーレイに状態配信  ★追加
        if self._overlay.is_running and action:
            topic_state = self.topic_engine.get_state_summary()
            clock_state = self.clock.tick() if self.clock.is_live else {}
            self._overlay.broadcast_state(
                char_state=dict(self.char_state),
                topic_info=topic_state.get('active', {}),
                clock_info=clock_state,
            )
            # 字幕は再生前に送信済み（_play_prepared内）
            # フェーズ変化の通知
            active = topic_state.get('active', {})
            if active.get('phase') and active.get('topic'):
                self._overlay.broadcast_phase_change(
                    phase=active.get('phase', ''),
                    topic=active.get('topic', ''),
                    heat=active.get('heat', 0),
                )
                # 話題が変わったらtopic_changeを配信
                current_topic = active.get('topic', '')
                if current_topic and current_topic != self._last_overlay_topic:
                    self._last_overlay_topic = current_topic
                    # topic_engineからキーワードを取得
                    kw = []
                    if self.topic_engine.active_topic:
                        kw = self.topic_engine.active_topic.keywords[:5]
                    self._overlay.broadcast_topic_change(
                        topic=current_topic,
                        keywords=kw,
                    )
                    # AI画像→動画チェーンをトリガー（Flux画像→即表示→Kling動画化）
                    # ★video_genは使わない（image_genがFlux→Klingチェーンを内包）
                    if self._image_gen.is_enabled:
                        asyncio.create_task(
                            self._image_gen.on_topic_change(current_topic, kw)
                        )
                    # ★クリップセレクター: 話題変更 → mood クリップに切替
                    if self._clip_selector.has_clips:
                        topic_key = self._find_topic_key(current_topic)
                        self._clip_selector.on_topic_change(topic_key)

                    # ★オーロラに話題変更バースト通知
                    if self._overlay.is_running:
                        self._overlay._broadcast({
                            'type': 'topic_change',
                            'topic': current_topic,
                        })

    # ── LLM生成関数（autonomous_talk用ラッパー）────────

    def _find_topic_key(self, topic_text: str) -> str:
        """話題テキストをClipSelectorに渡す（v3: そのまま渡す）"""
        return topic_text or ''

    async def _clip_timer_loop(self):
        """10-15秒ごとにクリップを自動切替"""
        try:
            while self._is_running:
                await asyncio.sleep(12)
                if not self._is_running:
                    break
                topic = ''
                if self.topic_engine.active_topic:
                    topic = self.topic_engine.active_topic.topic
                self._clip_selector.on_timer(topic)
        except asyncio.CancelledError:
            pass

    async def _generate_for_autonomous(self, **kwargs) -> str:
        """autonomous_talkが呼ぶLLM生成関数。配信状況とコメントを統合する"""
        # 配信状況を構築
        clock_state = self.clock.tick() if self.clock.is_live else {}
        elapsed = clock_state.get('elapsed_min', 0)
        comment_silence = clock_state.get('comment_silence_sec', 0)
        total_speaks = clock_state.get('total_speaks', 0)
        fatigue = clock_state.get('fatigue', 0)
        total_comments = len(self._recent_comments)

        situation_hint = f'\n\n【今の配信状況】\n'
        situation_hint += f'配信経過: {elapsed:.0f}分\n'
        situation_hint += f'コメント総数: {total_comments}件\n'

        if comment_silence > 120:
            situation_hint += (
                f'最後のコメントから{comment_silence/60:.0f}分経過。\n'
                'テンション落として、ぼそぼそ話す。短めに。\n'
                '「誰もいない」「一人で考える」とは言わない。ただ普通に話題を続ける。\n'
            )
        elif comment_silence > 60:
            situation_hint += (
                f'コメントしばらく来てない（{comment_silence:.0f}秒）。\n'
                'ちょっと静かめに。話題を続けつつ、たまに質問を混ぜる。\n'
            )
        elif total_comments == 0:
            situation_hint += (
                'まだコメント0件。\n'
                '気にしてない風で普通に話す。「誰かいる？」とか聞かない。\n'
            )

        if fatigue > 50:
            situation_hint += f'疲労度: {fatigue:.0f}/100。だるくなってきた。\n'

        kwargs['prompt_hint'] = kwargs.get('prompt_hint', '') + situation_hint

        # Zepから記憶コンテキストを取得  ★Phase8追加
        if self._zep.is_enabled and self._pending_comments:
            # コメントしたユーザーの記憶を取得
            last_user = self._pending_comments[-1].get('user_id', '')
            if last_user:
                zep_context = await self._zep.get_context(user_id=last_user)
                if zep_context:
                    kwargs['prompt_hint'] = kwargs.get('prompt_hint', '') + zep_context

        # 未処理コメントがあれば統合
        if self._pending_comments:
            comments_text = '\n'.join(
                f'- {c["user_id"]}: 「{c["text"]}」'
                for c in self._pending_comments
            )
            comment_hint = (
                f'\n【視聴者コメント（読み上げて反応すること）】\n{comments_text}\n'
                f'コメントを自然に拾う。「○○さんが〜って」みたいに。\n'
                f'全部拾わなくていい。気になったのだけ。\n'
            )
            kwargs['prompt_hint'] = kwargs.get('prompt_hint', '') + comment_hint
            self._pending_comments.clear()

        return await self.llm_generate(**kwargs)

    # ── YouTube Chat コールバック ────────────────────────  ★追加

    async def _on_youtube_comment(self, comment: ChatComment):
        """YouTubeChatPollerからのコールバック → on_comment()に統合"""
        await self.on_comment(
            text=comment.text,
            user_id=comment.author,
            is_superchat=comment.is_superchat,
        )

    # ── デバッグ ─────────────────────────────────────

    def get_status(self) -> dict:
        """現在のパイプライン状態"""
        clock_state = self.clock.tick() if self.clock.is_live else {}
        return {
            'is_running': self._is_running,
            'clock': clock_state,
            'char_state': dict(self.char_state),
            'topic': self.topic_engine.get_state_summary(),
            'voice_engine': self.voice.active_engine,
            'vtube_connected': (
                self._vtube is not None and self._vtube.is_connected
                if self._vtube else False
            ),
            'comment_queue_size': self._comment_queue.qsize(),
            'youtube_chat_active': (  # ★追加
                self._youtube_poller is not None and self._youtube_poller._running
                if self._youtube_poller else False
            ),
            'zep_memory_active': self._zep.is_enabled,  # ★Phase8追加
            'overlay_active': self._overlay.is_running,  # ★ビジュアルオーバーレイ
            'overlay_clients': self._overlay.client_count,
            'video_gen_enabled': self._video_gen.is_enabled,  # ★AI動画
            'video_cache_count': self._video_gen.get_cached_count(),
            'image_gen_enabled': self._image_gen.is_enabled,  # ★AI画像
            'image_cache_count': self._image_gen.get_cached_count(),
        }
