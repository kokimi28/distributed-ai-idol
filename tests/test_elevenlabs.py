# tests/test_elevenlabs.py
"""
ElevenLabs切替テスト

1. PCM→WAV変換が正しく動作するか
2. health_checkがプレースホルダーキーを拒否するか
3. VoicePipelineのフォールバック機構
4. emotion_to_voiceの出力がElevenLabsパラメータ範囲内か
"""

import asyncio
import io
import wave
from voice.synthesizer import (
    ElevenLabsSynthesizer, AivisSynthesizer,
    VoicePipeline, VoiceSettings, AudioPlayer,
)
from character.emotion_to_voice import convert_emotion_to_voice


def test_pcm_to_wav():
    """PCMデータをWAVに変換できるか"""
    # 1秒分のダミーPCMデータ（24kHz, 16bit mono）
    import struct
    sample_rate = 24000
    duration = 0.1  # 100ms
    num_samples = int(sample_rate * duration)
    # サイン波を生成
    import math
    pcm_bytes = b''
    for i in range(num_samples):
        sample = int(16000 * math.sin(2 * math.pi * 440 * i / sample_rate))
        pcm_bytes += struct.pack('<h', sample)

    # 変換
    wav_data = ElevenLabsSynthesizer._pcm_to_wav(pcm_bytes, sample_rate)

    # WAVとして読めるか確認
    buf = io.BytesIO(wav_data)
    with wave.open(buf, 'rb') as wf:
        assert wf.getnchannels() == 1, f'チャンネル数: {wf.getnchannels()}'
        assert wf.getframerate() == sample_rate, f'サンプルレート: {wf.getframerate()}'
        assert wf.getsampwidth() == 2, f'サンプル幅: {wf.getsampwidth()}'
        frames = wf.readframes(wf.getnframes())
        assert len(frames) == len(pcm_bytes), f'フレーム長不一致: {len(frames)} vs {len(pcm_bytes)}'

    print(f'[OK] PCM→WAV変換: {len(pcm_bytes)}bytes PCM → {len(wav_data)}bytes WAV')


def test_health_check_rejects_placeholder():
    """プレースホルダーキーがhealth_checkで拒否されるか"""
    synth = ElevenLabsSynthesizer(api_key='xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx')
    result = asyncio.run(synth.health_check())
    assert result == False, 'プレースホルダーキーが通ってしまった'
    print('[OK] プレースホルダーキーはhealth_checkで拒否される')

    synth2 = ElevenLabsSynthesizer(api_key='')
    result2 = asyncio.run(synth2.health_check())
    assert result2 == False, '空キーが通ってしまった'
    print('[OK] 空キーもhealth_checkで拒否される')


def test_emotion_to_voice_range():
    """emotion_to_voiceの出力がElevenLabsパラメータ範囲内か"""
    # 極端な感情状態でテスト
    test_cases = [
        ('joy=100', {'joy': 100, 'sadness': 0}, 'broadcast'),
        ('sadness=100', {'sadness': 100, 'joy': 0}, 'private'),
        ('anger=100', {'anger': 100}, 'broadcast'),
        ('全部50', {'joy': 50, 'sadness': 50, 'anger': 50, 'fatigue': 50}, 'broadcast'),
        ('ニュートラル', {'joy': 0, 'sadness': 0}, 'broadcast'),
    ]

    for label, emotions, mode in test_cases:
        params = convert_emotion_to_voice(emotions, mode)
        for key in ('stability', 'similarity_boost', 'style'):
            val = params[key]
            assert 0.0 <= val <= 1.0, f'{label}: {key}={val} が範囲外'
        print(f'[OK] {label} ({mode}): stability={params["stability"]:.3f}, '
              f'sim_boost={params["similarity_boost"]:.3f}, style={params["style"]:.3f}')


def test_voice_pipeline_fallback():
    """VoicePipelineのフォールバックエンジン取得"""
    pipeline = VoicePipeline(prefer_engine='elevenlabs')
    pipeline.active_engine = 'elevenlabs'
    fallback = pipeline._get_fallback_engine()
    assert fallback == 'aivispeech', f'フォールバック先が不正: {fallback}'
    print('[OK] ElevenLabs→AivisSpeechフォールバック確認')

    pipeline2 = VoicePipeline(prefer_engine='aivispeech')
    pipeline2.active_engine = 'aivispeech'
    fallback2 = pipeline2._get_fallback_engine()
    assert fallback2 == 'elevenlabs', f'フォールバック先が不正: {fallback2}'
    print('[OK] AivisSpeech→ElevenLabsフォールバック確認')




if __name__ == '__main__':
    print('=== ElevenLabs切替テスト ===\n')

    test_pcm_to_wav()
    test_health_check_rejects_placeholder()
    test_emotion_to_voice_range()
    test_voice_pipeline_fallback()

    print('\n=== 全テスト成功 ===')
