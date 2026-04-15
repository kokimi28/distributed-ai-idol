# tests/test_youtube_api.py  YouTube Data API接続テスト
import os
from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

def test_youtube_connection():
    api_key = os.getenv('YOUTUBE_API_KEY')
    assert api_key and not api_key.startswith('AIzaSyx'), 'APIキーが未設定またはプレースホルダーのまま'
    
    youtube = build('youtube', 'v3', developerKey=api_key)
    
    # テスト1: API接続確認（適当な動画カテゴリを取得）
    req = youtube.videoCategories().list(part='snippet', regionCode='JP')
    resp = req.execute()
    assert 'items' in resp, 'APIレスポンスにitemsがない'
    print(f'API接続OK: {len(resp["items"])}カテゴリ取得')
    
    # テスト2: チャンネルID確認（.envに設定済みなら）
    channel_id = os.getenv('YOUTUBE_CHANNEL_ID')
    if channel_id and not channel_id.startswith('UCx'):
        req2 = youtube.channels().list(part='snippet', id=channel_id)
        resp2 = req2.execute()
        if resp2.get('items'):
            name = resp2['items'][0]['snippet']['title']
            print(f'チャンネル確認OK: {name}')
        else:
            print(f'チャンネルID {channel_id} が見つかりません（後で設定でOK）')
    else:
        print('YOUTUBE_CHANNEL_IDは未設定（配信時に設定すればOK）')
    
    print('YouTube API接続テスト: 成功')

test_youtube_connection()