# tests/integration/test_4_vbcable.py
"""テスト4: VB-CABLE経由の音声出力テスト"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def test_4a_device_list():
    """4-1: VB-CABLEが認識されるか確認"""
    print('=== 4-1: 出力デバイス一覧 ===')
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        import pyaudio

    pa = pyaudio.PyAudio()
    found = False
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info['maxOutputChannels'] > 0:
            marker = ' ★' if 'cable' in info['name'].lower() else ''
            print('  [%d] %s%s' % (i, info['name'], marker))
            if 'cable input' in info['name'].lower():
                found = True
    pa.terminate()
    print()
    if found:
        print('VB-CABLE (CABLE Input): 見つかった')
    else:
        print('VB-CABLE (CABLE Input): 見つからない')
        print('  → VB-CABLEがインストールされているか確認')
        print('  → PCを再起動してみる')
    return found


async def test_4b_send_audio():
    """4-2: VB-CABLEに音声を送信"""
    print()
    print('=== 4-2: VB-CABLE音声送信 ===')
    from voice.synthesizer import AivisSynthesizer, AudioPlayer

    synth = AivisSynthesizer(base_url='http://127.0.0.1:10101', speaker_id=0)
    ok = await synth.health_check()
    if not ok:
        print('AivisSpeechに接続できません。先にテスト3を通してください。')
        return

    result = await synth.synthesize('VB-CABLE経由の音声テストです。聞こえていますか。')

    player = AudioPlayer(device_name='CABLE Input')
    player._find_device()
    if player._device_index is None:
        print('CABLE Input が見つかりません')
        return

    print('CABLE Input デバイス: [%d]' % player._device_index)
    print('VB-CABLEに音声を送信中...')
    player.play_wav(result.audio_data)
    print('送信完了')
    print()
    print('※ この音声はPCのスピーカーからは聞こえません（VB-CABLEに行くため）')
    print('※ OBSの音声ミキサーでレベルが動けばOK')
    player.close()


if __name__ == '__main__':
    found = test_4a_device_list()
    if found:
        asyncio.run(test_4b_send_audio())
