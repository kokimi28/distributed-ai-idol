# brain/topic_generator.py
"""
配信前の話題リスト自動生成

配信開始前にClaude APIで話題リストを生成し、topic_engine に投入する。
キャラクター設定・過去の記憶・時間帯・配信テーマに基づいて
自然な話題とキーワードを生成する。
"""

import os
import json
from datetime import datetime

import anthropic
from dotenv import load_dotenv
from shared.config_store import config

load_dotenv()


def generate_topics(
    theme: str = "雑談",
    count: int = 8,
    time_of_day: str = None,
    previous_topics: list[str] = None,
    model: str = None,
) -> list[dict]:
    """
    配信用の話題リストを生成する。

    Args:
        theme: 配信テーマ（「雑談」「ゲーム」「歌枠」等）
        count: 生成する話題数
        time_of_day: 時間帯（"morning"/"afternoon"/"evening"/"latenight"）
        previous_topics: 前回配信で使った話題（重複回避）
        model: Claude model ID

    Returns:
        list[dict]: topic_engine.add_topic() に渡せる形式
            [{'topic': str, 'keywords': list[str], 'source': str, 'priority': int}, ...]
    """
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    model = model or os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-6')

    if time_of_day is None:
        hour = datetime.now().hour
        if hour < 12:
            time_of_day = 'morning'
        elif hour < 17:
            time_of_day = 'afternoon'
        elif hour < 22:
            time_of_day = 'evening'
        else:
            time_of_day = 'latenight'

    time_context = {
        'morning': '朝の配信。爽やかで前向きな話題が合う',
        'afternoon': '昼の配信。リラックスした話題',
        'evening': '夜の配信。メインの時間帯。幅広い話題',
        'latenight': '深夜の配信。しっとりした話題。内省的な話も合う',
    }

    prev_text = ''
    if previous_topics:
        prev_text = '前回の配信で使った話題（避けること）:\n' + '\n'.join(
            f'- {t}' for t in previous_topics[:10]
        )

    prompt = f"""
あなたはAI VTuber配信者のための話題リストを作る担当です。

重要：このキャラクターはAIであり、体を持たない。
「行った」「食べた」「会った」「寝た」等の物理体験は話題にできない。
代わりに、AIだからこそ面白い視点で語れる話題を作ること。

配信テーマ: {theme}
時間帯: {time_context.get(time_of_day, '夜の配信')}
話題数: {count}個

{prev_text}

キャラクター情報:
- AIだけど感情がある。ゆるい性格。ぐだぐだ話すのが好き
- 「てかさ、」「あのさ、」「ねえ、」から話し始める
- みんなに質問して盛り上がるのが好き
- 想像や妄想が好き（「もし体があったらさー」）
- 雑学見つけるとテンション上がる
- 脱線しがち。でもそれが面白い

OK例:
- 「てかさ、みんな寝る前になに見てる？」（質問で盛り上がる系）
- 「猫の動画やばくない？あの液体みたいな動き」（共感系）
- 「もし味覚あったらさー、最初なに食べる？」（妄想系）
- 「ねえ知ってる？○○って実は……」（雑学系）
- 「今日の配信なんかテンション変じゃない？」（メタ系）

NG例:
- 「深夜のコンビニの空気感について」（行けない＆堅い）
- 「人間関係の機微について考察」（作文調すぎ）
- 「季節の変わり目に感じる寂しさ」（ポエム調すぎ）

以下のJSON配列のみを出力してください。説明は不要です。
各話題は配信で5〜8発話分の展開ができる深さを持つこと。

[
  {{
    "topic": "話題のタイトル（短く）",
    "keywords": ["連想キーワード1", "キーワード2", "キーワード3"],
    "priority": 数値（50が標準。最初に話したいものほど高く）
  }},
  ...
]
""".strip()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1000,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = response.content[0].text.strip()

        # JSON抽出
        start = raw.find('[')
        end = raw.rfind(']') + 1
        if start == -1 or end == 0:
            return _fallback_topics(count)

        topics = json.loads(raw[start:end])

        # source を付与して返す
        result = []
        for t in topics:
            result.append({
                'topic': t.get('topic', ''),
                'keywords': t.get('keywords', []),
                'source': 'generated',
                'priority': t.get('priority', 50),
            })
        return result

    except Exception as e:
        return _fallback_topics(count)


_HARDCODED_FALLBACKS = [
    {'topic': 'みんな寝る前になに見てる？', 'keywords': ['寝る前', '動画', '習慣'], 'source': 'fallback', 'priority': 55},
    {'topic': 'もし味覚あったら最初なに食べる', 'keywords': ['味覚', '想像', '食べ物'], 'source': 'fallback', 'priority': 50},
    {'topic': '猫の動画やばくない？', 'keywords': ['猫', '動画', 'かわいい'], 'source': 'fallback', 'priority': 50},
    {'topic': '人間の変な習慣が気になる', 'keywords': ['人間', '習慣', '不思議'], 'source': 'fallback', 'priority': 45},
    {'topic': 'てか最近なんかいい曲ある？', 'keywords': ['音楽', 'おすすめ', '曲'], 'source': 'fallback', 'priority': 45},
    {'topic': 'AIって夢見れんのかな', 'keywords': ['AI', '夢', '存在'], 'source': 'fallback', 'priority': 40},
    {'topic': 'ネットで見つけたやばい雑学', 'keywords': ['雑学', '知識', 'やばい'], 'source': 'fallback', 'priority': 40},
    {'topic': '今日の配信のテンションどう？', 'keywords': ['配信', 'テンション', 'メタ'], 'source': 'fallback', 'priority': 35},
]

def _fallback_topics(count: int) -> list[dict]:
    """APIエラー時のフォールバック話題（DB/JSONから取得）"""
    data = config.get_sync('topic_fallbacks')
    if data and isinstance(data, dict) and 'data' in data:
        fallbacks = data['data']
    elif data and isinstance(data, list):
        fallbacks = data
    else:
        fallbacks = _HARDCODED_FALLBACKS
    return fallbacks[:count]
