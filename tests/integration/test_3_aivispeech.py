# tests/integration/test_3_aivispeech.py
"""テスト3: AivisSpeech接続テスト"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import aiohttp

BASE_URL = 'http://127.0.0.1:10101'


async def find_speakers():
    """利用可能な話者を一覧表示"""
    print('=== AivisSpeech 話者一覧 ===')
    async with aiohttp.ClientSession() as session:
        async with session.get(BASE_URL + '/speakers', timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status != 200:
                print('話者一覧の取得に失敗: status=%d' % resp.status)
                return None
            speakers = await resp.json()

    first_id = None
    for speaker in speakers:
        name = speaker.get('name', '不明')
        styles = speaker.get('styles', [])
        for style in styles:
            sid = style.get('id', '?')
            sname = style.get('name', '?')
            print('  speaker_id=%s : %s - %s' % (sid, name, sname))
            if first_id is None:
                first_id = sid
    print()
    return first_id


async def main():
    # ヘルスチェック
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL + '/version', timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    ver = await resp.text()
                    print('AivisSpeech接続: OK (version=%s)' % ver.strip().strip('"'))
                else:
                    print('AivisSpeech接続: NG (status=%d)' % resp.status)
                    return
    except Exception as e:
        print('AivisSpeech接続: NG (%s)' % e)
        print('  → AivisSpeechが起動しているか確認')
        return

    # 話者一覧を取得
    speaker_id = await find_speakers()
    if speaker_id is None:
        print('話者が見つかりません')
        return

    print('最初の話者 speaker_id=%s で音声合成を試みます...' % speaker_id)
    print()

    # audio_query
    async with aiohttp.ClientSession() as session:
        url = BASE_URL + '/audio_query'
        params = {'text': 'テスト。こんばんは。', 'speaker': speaker_id}
        async with session.post(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                body = await resp.text()
                print('audio_query 失敗: status=%d' % resp.status)
                print('  URL: %s?text=...&speaker=%s' % (url, speaker_id))
                print('  応答: %s' % body[:200])
                return
            query = await resp.json()
            print('audio_query: OK')

        # synthesis
        import json
        url2 = BASE_URL + '/synthesis'
        async with session.post(url2, params={'speaker': speaker_id},
                                headers={'Content-Type': 'application/json'},
                                data=json.dumps(query),
                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                body = await resp.text()
                print('synthesis 失敗: status=%d' % resp.status)
                print('  応答: %s' % body[:200])
                return
            audio_data = await resp.read()
            print('synthesis: OK (%d bytes)' % len(audio_data))

    # 保存
    with open('test_voice.wav', 'wb') as f:
        f.write(audio_data)
    print()
    print('test_voice.wav を保存しました。')
    print('再生: Start-Process test_voice.wav')
    print()
    print('★ synthesizer.py を更新してください:')
    print('  AivisSynthesizer(base_url="%s", speaker_id=%s)' % (BASE_URL, speaker_id))


asyncio.run(main())
