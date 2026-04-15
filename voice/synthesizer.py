# voice/synthesizer.py
"""
音声合成抽象レイヤー

AivisSpeech（無料・MVP）とElevenLabs（有料・本番）を統一インターフェースで切替。
生成した音声をpyaudioでVB-CABLEに出力する。

設計:
- SynthesizerBase: 抽象基底クラス
- AivisSynthesizer: ローカルHTTP API（VOICEVOX互換）
- ElevenLabsSynthesizer: クラウドAPI + 感情パラメータ連動
- AudioPlayer: pyaudioでVB-CABLEへ出力
"""

import io
import os
import json
import wave
import struct
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
from dotenv import load_dotenv
from shared.config_store import config

load_dotenv()


# ── データ型 ────────────────────────────────────────────

@dataclass
class VoiceSettings:
    """ElevenLabs互換の音声パラメータ"""
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.3
    use_speaker_boost: bool = True


@dataclass
class SynthResult:
    """音声合成の結果"""
    audio_data: bytes              # PCM or WAV バイナリ
    format: str = "wav"            # "wav" or "pcm"
    sample_rate: int = 24000
    text: str = ""
    engine: str = ""
    duration_ms: float = 0.0


# ── 抽象基底 ────────────────────────────────────────────

class SynthesizerBase(ABC):
    """音声合成エンジンの共通インターフェース"""

    @abstractmethod
    async def synthesize(self, text: str,
                         voice_settings: Optional[VoiceSettings] = None
                         ) -> SynthResult:
        """テキストを音声に変換する"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """エンジンが利用可能か確認"""
        ...

    @property
    @abstractmethod
    def engine_name(self) -> str:
        ...


# ── AivisSpeech 実装 ────────────────────────────────────

class AivisSynthesizer(SynthesizerBase):
    """
    AivisSpeech（VOICEVOX互換API）による音声合成。
    ローカルで動作、無料。CORSモードで起動が必要。

    API Flow:
      1. POST /audio_query?text=...&speaker=... → クエリJSON
      2. POST /synthesis?speaker=... (body=クエリJSON) → WAV bytes

    スタイル切替:
      AivisSpeechは感情パラメータ(stability等)に対応していないが、
      「まお」のスタイル（ノーマル/あまあま/おちつき/せつなめ等）を
      感情状態に応じて切り替えることで、擬似的な感情表現を実現する。
    """

    # まお のスタイル別 speaker_id
    # .env や設定ファイルで上書き可能にする想定
    STYLE_MAP = {
        'normal':   int(os.getenv('AIVIS_STYLE_NORMAL',   '888753760')),  # ノーマル
        'flat':     int(os.getenv('AIVIS_STYLE_FLAT',      '888753761')),  # ふつー
        'sweet':    int(os.getenv('AIVIS_STYLE_SWEET',     '888753762')),  # あまあま
        'calm':     int(os.getenv('AIVIS_STYLE_CALM',      '888753763')),  # おちつき
        'teasing':  int(os.getenv('AIVIS_STYLE_TEASING',   '888753764')),  # からかい
        'sad':      int(os.getenv('AIVIS_STYLE_SAD',       '888753765')),  # せつなめ
    }

    def __init__(self,
                 base_url: str = "http://127.0.0.1:10101",
                 speaker_id: int = None):
        self.base_url = base_url.rstrip("/")
        self.speaker_id = speaker_id or self.STYLE_MAP['normal']

    @property
    def engine_name(self) -> str:
        return "AivisSpeech"

    async def health_check(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/version", timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    def _select_style(self, voice_settings: Optional[VoiceSettings]) -> int:
        """voice_settingsからAivisSpeechのスタイルを選択する。
        閾値はconfig_storeから読み込み（ホットリロード可能）"""
        if voice_settings is None:
            return self.speaker_id

        s = voice_settings.stability
        st = voice_settings.style

        # config_storeから閾値を取得
        vs_data = config.get_sync('voice_settings')
        thresholds = (vs_data or {}).get('aivispeech_style_thresholds', {})

        # 閾値ベースで判定（fallback: ハードコード値）
        sweet_th = thresholds.get('sweet', {})
        if s < sweet_th.get('stability_lt', 0.35) and st > sweet_th.get('style_gt', 0.4):
            return self.STYLE_MAP['sweet']

        teasing_th = thresholds.get('teasing', {})
        if s < teasing_th.get('stability_lt', 0.35):
            return self.STYLE_MAP['teasing']

        sad_th = thresholds.get('sad', {})
        if s > sad_th.get('stability_gt', 0.65) and st < sad_th.get('style_lt', 0.2):
            return self.STYLE_MAP['sad']

        calm_th = thresholds.get('calm', {})
        if s > calm_th.get('stability_gt', 0.65):
            return self.STYLE_MAP['calm']

        return self.STYLE_MAP['normal']

    async def synthesize(self, text: str,
                         voice_settings: Optional[VoiceSettings] = None
                         ) -> SynthResult:
        """
        AivisSpeechで音声合成。
        voice_settingsのパラメータからスタイルを自動選択する:
          - stability低 + style高 → あまあま or からかい（興奮・喜び系）
          - stability高 + style低 → せつなめ or おちつき（静か系）
          - それ以外 → ノーマル
        """
        # スタイル選択
        sid = self._select_style(voice_settings)

        async with aiohttp.ClientSession() as session:
            # Step 1: audio_query
            async with session.post(
                f"{self.base_url}/audio_query",
                params={"text": text, "speaker": sid},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(
                        f"AivisSpeech audio_query failed: {resp.status}")
                query = await resp.json()

            # 速度・ポーズの調整（音質を維持するため最小限の変更に留める）
            # ※pitchScaleは音質劣化の原因になるので変更しない
            # ※speedScaleも大きく変えると劣化するので控えめに
            query["speedScale"] = 0.92   # やや落ち着いたペース（デフォルト1.0）
            query["pitchScale"] = 0.0    # 変更しない（音質維持）
            query["volumeScale"] = 1.0   # フルボリューム（OBS側で調整）
            query["pauseLengthScale"] = 1.4  # 文末ポーズやや長め

            # Step 2: synthesis
            async with session.post(
                f"{self.base_url}/synthesis",
                params={"speaker": sid},
                headers={"Content-Type": "application/json"},
                data=json.dumps(query),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(
                        f"AivisSpeech synthesis failed: {resp.status}")
                audio_data = await resp.read()

        return SynthResult(
            audio_data=audio_data,
            format="wav",
            sample_rate=24000,
            text=text,
            engine="AivisSpeech",
        )


# ── ElevenLabs 実装 ─────────────────────────────────────

class ElevenLabsSynthesizer(SynthesizerBase):
    """
    ElevenLabs API による音声合成。
    感情パラメータ（VoiceSettings）を動的に制御可能。

    PCMフォーマットで取得し、WAVヘッダーを付与して返す。
    これによりMP3デコーダー不要でAudioPlayerと互換。
    """

    def __init__(self,
                 api_key: str = None,
                 voice_id: str = None,
                 model_id: str = None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY", "")
        self.voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", "")
        self.model_id = model_id or os.getenv(
            "ELEVENLABS_MODEL_BROADCAST", "eleven_flash_v2_5")
        self.base_url = "https://api.elevenlabs.io/v1"
        self._sample_rate = 24000  # PCM出力のサンプルレート

    @property
    def engine_name(self) -> str:
        return "ElevenLabs"

    async def health_check(self) -> bool:
        if not self.api_key or self.api_key.startswith("xxxx"):
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/voices",
                    headers={"xi-api-key": self.api_key},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    @staticmethod
    def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000,
                    channels: int = 1, sample_width: int = 2) -> bytes:
        """生PCMデータにWAVヘッダーを付与する"""
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
        return buf.getvalue()

    async def synthesize(self, text: str,
                         voice_settings: Optional[VoiceSettings] = None
                         ) -> SynthResult:
        """
        ElevenLabsで音声合成。PCMで取得しWAV変換して返す。
        voice_settingsで感情パラメータを動的制御。
        """
        settings = voice_settings or VoiceSettings()

        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": settings.stability,
                "similarity_boost": settings.similarity_boost,
                "style": settings.style,
                "use_speaker_boost": settings.use_speaker_boost,
            },
        }

        # PCMフォーマットで取得（MP3デコーダー不要）
        output_format = f"pcm_{self._sample_rate}"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/text-to-speech/{self.voice_id}"
                f"?output_format={output_format}",
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                data=json.dumps(payload),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(
                        f"ElevenLabs synthesis failed: {resp.status} {error_text}")
                pcm_data = await resp.read()

        # PCM → WAV変換（AudioPlayerと互換）
        wav_data = self._pcm_to_wav(pcm_data, self._sample_rate)

        return SynthResult(
            audio_data=wav_data,
            format="wav",
            sample_rate=self._sample_rate,
            text=text,
            engine="ElevenLabs",
        )


# ── 音声出力（VB-CABLE） ───────────────────────────────

class AudioPlayer:
    """
    pyaudioを使ってVB-CABLEに音声を出力する。
    Windowsでのみ動作。テスト時はplayをスキップ可能。
    """

    def __init__(self, device_name: str = "CABLE Input"):
        self.device_name = device_name
        self._pa = None
        self._device_index = None

    def _find_device(self):
        """VB-CABLEのデバイスインデックスを探す"""
        try:
            import pyaudio
            self._pa = pyaudio.PyAudio()
        except ImportError:
            # pyaudiowpatch でも試す
            try:
                import pyaudiowpatch as pyaudio
                self._pa = pyaudio.PyAudio()
            except ImportError:
                return None

        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if self.device_name.lower() in info["name"].lower():
                if info["maxOutputChannels"] > 0:
                    self._device_index = i
                    return i
        return None

    def play_wav(self, wav_data: bytes):
        """WAVバイナリを再生する"""
        if self._pa is None:
            self._find_device()
        if self._pa is None:
            raise RuntimeError("pyaudio not available")

        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            stream = self._pa.open(
                format=self._pa.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True,
                output_device_index=self._device_index,
                frames_per_buffer=4096,
            )
            chunk = 4096
            data = wf.readframes(chunk)
            while data:
                stream.write(data)
                data = wf.readframes(chunk)
            stream.stop_stream()
            stream.close()

    def close(self):
        if self._pa:
            self._pa.terminate()
            self._pa = None


# ── 統合クラス ──────────────────────────────────────────

class VoicePipeline:
    """
    音声合成パイプラインの統合エントリポイント。
    エンジン選択 → 合成 → 再生 を一括で行う。
    """

    def __init__(self, prefer_engine: str = "aivispeech"):
        """
        Args:
            prefer_engine: "aivispeech" or "elevenlabs"
        """
        self.engines: dict[str, SynthesizerBase] = {}
        self.player: Optional[AudioPlayer] = None
        self.active_engine: Optional[str] = None

        # エンジン登録
        self.engines["aivispeech"] = AivisSynthesizer()
        self.engines["elevenlabs"] = ElevenLabsSynthesizer()
        self.prefer_engine = prefer_engine

    async def initialize(self) -> str:
        """
        利用可能なエンジンを検出してアクティブにする。
        Returns: アクティブになったエンジン名
        """
        # 優先エンジンから試す
        order = [self.prefer_engine]
        for name in self.engines:
            if name not in order:
                order.append(name)

        for name in order:
            engine = self.engines.get(name)
            if engine and await engine.health_check():
                self.active_engine = name
                return engine.engine_name

        raise RuntimeError("利用可能な音声合成エンジンがありません")

    async def speak(self, text: str,
                    voice_settings: Optional[VoiceSettings] = None,
                    play_audio: bool = True) -> SynthResult:
        """
        テキストを音声合成し、（オプションで）再生する。
        アクティブエンジンが失敗した場合、代替エンジンにフォールバック。
        """
        if not self.active_engine:
            await self.initialize()

        engine = self.engines[self.active_engine]
        try:
            result = await engine.synthesize(text, voice_settings)
        except Exception as e:
            # アクティブエンジン失敗 → 代替を試す
            fallback_name = self._get_fallback_engine()
            if fallback_name:
                fallback = self.engines[fallback_name]
                try:
                    result = await fallback.synthesize(text, voice_settings)
                except Exception:
                    raise
            else:
                raise

        if play_audio and result.format == "wav":
            if self.player is None:
                self.player = AudioPlayer()
            try:
                self.player.play_wav(result.audio_data)
            except Exception as e:
                # 再生失敗は致命的ではない（テスト環境等）
                pass

        return result

    async def switch_engine(self, engine_name: str) -> bool:
        """エンジンを手動切替"""
        engine = self.engines.get(engine_name)
        if engine and await engine.health_check():
            self.active_engine = engine_name
            return True
        return False

    def _get_fallback_engine(self) -> Optional[str]:
        """アクティブ以外で利用可能なエンジン名を返す"""
        for name in self.engines:
            if name != self.active_engine:
                return name
        return None

    def close(self):
        if self.player:
            self.player.close()
