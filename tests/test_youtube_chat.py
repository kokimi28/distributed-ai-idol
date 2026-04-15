# tests/test_youtube_chat.py  YouTube Chatポーラー単体テスト
import asyncio
from datetime import datetime, timezone
from broadcast.youtube_chat import YouTubeChatPoller, ChatComment

collected = []

async def mock_on_comment(comment: ChatComment):
    collected.append(comment)
    print(f'  受信: [{comment.author}] {comment.text}')

def test_poller_init():
    """初期化テスト"""
    poller = YouTubeChatPoller(on_comment=mock_on_comment)
    assert poller._polling_interval == 5.0
    assert poller._running is False
    assert poller._total_comments == 0
    print('初期化テスト: OK')

def test_parse_comment():
    """コメントパーステスト"""
    poller = YouTubeChatPoller(on_comment=mock_on_comment)
    
    # 通常コメント
    item = {
        'snippet': {
            'type': 'textMessageEvent',
            'publishedAt': '2026-03-23T12:00:00Z',
            'textMessageDetails': {'messageText': 'こんにちは！'}
        },
        'authorDetails': {
            'displayName': 'テストユーザー',
            'isChatMember': False
        }
    }
    comment = poller._parse_comment(item)
    assert comment is not None
    assert comment.author == 'テストユーザー'
    assert comment.text == 'こんにちは！'
    assert comment.is_superchat is False
    print(f'通常コメント解析: OK ({comment.author}: {comment.text})')
    
    # スーパーチャット
    item_sc = {
        'snippet': {
            'type': 'superChatEvent',
            'publishedAt': '2026-03-23T12:01:00Z',
            'superChatDetails': {
                'userComment': 'がんばれ！',
                'amountMicros': '500000000',
            }
        },
        'authorDetails': {
            'displayName': 'スパチャさん',
            'isChatMember': True
        }
    }
    sc = poller._parse_comment(item_sc)
    assert sc is not None
    assert sc.is_superchat is True
    assert sc.superchat_amount == 500.0
    assert sc.is_member is True
    print(f'スーパーチャット解析: OK ({sc.author}: ¥{sc.superchat_amount})')
    
    # 不明なタイプ（無視される）
    item_unknown = {
        'snippet': {'type': 'newSponsorEvent'},
        'authorDetails': {'displayName': 'x'}
    }
    result = poller._parse_comment(item_unknown)
    assert result is None
    print('不明タイプ除外: OK')

def test_api_connection():
    """API接続テスト（実際のAPIを叩く）"""
    poller = YouTubeChatPoller(on_comment=mock_on_comment)
    assert poller._api_key, 'YOUTUBE_API_KEYが未設定'
    
    from googleapiclient.discovery import build
    yt = build('youtube', 'v3', developerKey=poller._api_key)
    resp = yt.videoCategories().list(part='snippet', regionCode='JP').execute()
    assert 'items' in resp
    print(f'API接続: OK ({len(resp["items"])}カテゴリ)')

def test_callback_flow():
    """コールバックフローテスト（モックデータで on_comment が呼ばれるか）"""
    collected.clear()
    poller = YouTubeChatPoller(on_comment=mock_on_comment)
    
    # 手動でparse → callback
    item = {
        'snippet': {
            'type': 'textMessageEvent',
            'publishedAt': '2026-03-23T12:00:00Z',
            'textMessageDetails': {'messageText': 'えっ！まじで！'}
        },
        'authorDetails': {
            'displayName': '驚きさん',
            'isChatMember': False
        }
    }
    comment = poller._parse_comment(item)
    asyncio.run(mock_on_comment(comment))
    
    assert len(collected) == 1
    assert collected[0].text == 'えっ！まじで！'
    print('コールバックフロー: OK（反射層に渡せるコメント形式を確認）')

if __name__ == '__main__':
    test_poller_init()
    test_parse_comment()
    test_api_connection()
    test_callback_flow()
    print('\nYouTube Chatテスト: 全て成功')