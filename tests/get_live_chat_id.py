# tests/get_live_chat_id.py
"""配信中のliveChatIdを取得する"""

import os
from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

api_key = os.getenv('YOUTUBE_API_KEY')
yt = build('youtube', 'v3', developerKey=api_key)

# 方法1: チャンネルIDから検索
channel_id = os.getenv('YOUTUBE_CHANNEL_ID', '')
print(f'YOUTUBE_CHANNEL_ID: {channel_id or "(未設定)"}')

if channel_id and not channel_id.startswith('UCx'):
    print('\n方法1: チャンネルIDからライブ検索...')
    resp = yt.search().list(
        part='id,snippet',
        channelId=channel_id,
        eventType='live',
        type='video',
        maxResults=5,
    ).execute()

    items = resp.get('items', [])
    if items:
        video_id = items[0]['id']['videoId']
        title = items[0]['snippet']['title']
        print(f'  ライブ配信発見: {title} (videoId={video_id})')
    else:
        print('  ライブ配信が見つかりません')
        video_id = None
else:
    print('チャンネルID未設定。方法2を使います。')
    video_id = None

# 方法2: 手動でvideoIdを入力
if not video_id:
    print('\n方法2: YouTube Studioの配信URLから動画IDを入力')
    print('  YouTube Studio → ライブ配信 → 配信URLをコピー')
    print('  例: https://youtube.com/watch?v=XXXXXXXXXXX')
    print('  「v=」の後ろの文字列が動画IDです')
    video_id = input('\n動画ID（v=の後ろ）を入力: ').strip()
    if not video_id:
        print('動画IDが入力されませんでした')
        exit(1)

# videoIdからliveChatIdを取得
print(f'\nvideoId: {video_id}')
print('liveChatId取得中...')

video_resp = yt.videos().list(
    part='liveStreamingDetails,snippet',
    id=video_id,
).execute()

video_items = video_resp.get('items', [])
if not video_items:
    print(f'動画 {video_id} が見つかりません')
    exit(1)

title = video_items[0]['snippet']['title']
live_details = video_items[0].get('liveStreamingDetails', {})
live_chat_id = live_details.get('activeLiveChatId', '')

print(f'配信タイトル: {title}')
print(f'liveChatId: {live_chat_id}')

if live_chat_id:
    print(f'\n✅ 以下のコマンドで配信テストを開始できます:')
    print(f'python run_broadcast.py --chat-id={live_chat_id} --duration=10')
else:
    print('\n❌ liveChatIdが取得できませんでした')
    print('配信が限定公開で実行中か確認してください（非公開ではNG）')
