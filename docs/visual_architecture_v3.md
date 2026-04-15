# docs/visual_architecture_v3.md
# ビジュアルアーキテクチャ v3 - アイテムベース設計

## 問題の整理（v2の致命的欠陥）

1. **字幕が話す言葉全部のってない** → 字幕送信タイミングのバグ
2. **動画がループ** → 1話題3本では30秒で繰り返し
3. **部屋の構造がおかしい** → 毎回AI生成で家具の位置が変わる
4. **同じ動画が何度も** → 新規性がない

## 根本原因: 「話題ベース」が間違い

v2: 話題(猫) → 3クリップ(talking/activity/mood)
→ 3分間の話題で同じ30秒がループ

## 新アーキテクチャ: アイテムベース

### 核心思想
部屋は「生きた空間」。アイテム（物）がある。
まおはアイテムと関わる。話題はアイテムの組み合わせ。

### データモデル

```json
// room_state.json - まおの部屋の状態
{
  "layout": {
    "description": "永続的な部屋の構造",
    "camera_angle": "three-quarter from lower left",
    "fixed": ["wooden floor", "window with city view",
              "fairy lights on wall", "door on right"]
  },

  "furniture": {
    "desk": {
      "position": "by window, left side",
      "description": "wooden desk with laptop and small lamp",
      "added": "2026-01-01",
      "clips": [
        {"action": "typing on laptop", "cam": "B", "file": "desk_typing.mp4"},
        {"action": "leaning back stretching", "cam": "B", "file": "desk_stretch.mp4"},
        {"action": "looking at screen surprised", "cam": "A", "file": "desk_surprise.mp4"},
        {"action": "closing laptop, standing up", "cam": "B", "file": "desk_close.mp4"}
      ]
    },
    "bookshelf": {
      "position": "wall behind desk",
      "description": "tall bookshelf with books and small plants",
      "added": "2026-01-01",
      "clips": [
        {"action": "browsing books, pulls one out", "cam": "B", "file": "shelf_browse.mp4"},
        {"action": "reading standing, turns pages", "cam": "B", "file": "shelf_read.mp4"},
        {"action": "organizing books, rearranges", "cam": "C", "file": "shelf_organize.mp4"},
        {"action": "reaches high shelf on tiptoes", "cam": "B", "file": "shelf_reach.mp4"},
        {"action": "puts book back, picks another", "cam": "B", "file": "shelf_swap.mp4"}
      ]
    },
    "bed": {
      "position": "right corner",
      "description": "cozy bed with pillows and blanket",
      "added": "2026-01-01",
      "clips": [
        {"action": "flops onto bed face down", "cam": "C", "file": "bed_flop.mp4"},
        {"action": "lies reading on stomach, kicks legs", "cam": "B", "file": "bed_read.mp4"},
        {"action": "curled up hugging pillow", "cam": "C", "file": "bed_curl.mp4"},
        {"action": "sits up stretching, yawning", "cam": "B", "file": "bed_wake.mp4"},
        {"action": "scrolling phone on bed", "cam": "B", "file": "bed_phone.mp4"}
      ]
    }
  },

  "items": {
    "guitar": {
      "position": "leaning against bookshelf",
      "description": "acoustic guitar",
      "added": "2026-02-14",
      "clips": [
        {"action": "picks up guitar, tunes it", "cam": "B", "file": "guitar_tune.mp4"},
        {"action": "plays chords, concentrating", "cam": "B", "file": "guitar_play.mp4"},
        {"action": "hums along, casual strumming", "cam": "A", "file": "guitar_hum.mp4"},
        {"action": "puts guitar down, stretches hands", "cam": "B", "file": "guitar_put.mp4"}
      ]
    },
    "telescope": {
      "position": "by window, right side",
      "description": "small desktop telescope",
      "added": "2026-03-01",
      "clips": [
        {"action": "peers through telescope", "cam": "B", "file": "scope_peer.mp4"},
        {"action": "adjusts telescope angle", "cam": "B", "file": "scope_adjust.mp4"},
        {"action": "looks away amazed, back to scope", "cam": "A", "file": "scope_wow.mp4"}
      ]
    },
    "cat": {
      "position": "on cat cushion near bed",
      "description": "fluffy orange cat named mikan",
      "added": "2026-01-15",
      "clips": [
        {"action": "dangles toy for cat", "cam": "B", "file": "cat_play.mp4"},
        {"action": "cat jumps in lap, pets it", "cam": "A", "file": "cat_lap.mp4"},
        {"action": "watches cat sleep, smiles", "cam": "C", "file": "cat_watch.mp4"},
        {"action": "feeds cat treats", "cam": "B", "file": "cat_feed.mp4"},
        {"action": "holds cat up to camera", "cam": "A", "file": "cat_show.mp4"}
      ]
    },

    "mug": {
      "position": "on desk",
      "description": "favorite paw-print mug",
      "added": "2026-01-01",
      "clips": [
        {"action": "picks up mug, sips, sets down", "cam": "A", "file": "mug_sip.mp4"},
        {"action": "wraps both hands around warm mug", "cam": "A", "file": "mug_warm.mp4"},
        {"action": "carries mug to window", "cam": "B", "file": "mug_window.mp4"}
      ]
    },
    "headphones": {
      "position": "hanging on desk lamp",
      "description": "over-ear headphones with LED",
      "added": "2026-01-01",
      "clips": [
        {"action": "puts on headphones, bobs head", "cam": "A", "file": "hp_on.mp4"},
        {"action": "takes off headphones, reacts", "cam": "A", "file": "hp_off.mp4"},
        {"action": "adjusts volume, nods to beat", "cam": "B", "file": "hp_adjust.mp4"}
      ]
    },
    "plants": {
      "position": "windowsill",
      "description": "small potted succulents",
      "added": "2026-02-01",
      "clips": [
        {"action": "mists plants with spray bottle", "cam": "B", "file": "plant_mist.mp4"},
        {"action": "examines new growth closely", "cam": "A", "file": "plant_look.mp4"},
        {"action": "repots a succulent", "cam": "B", "file": "plant_repot.mp4"}
      ]
    }
  },

  "talking": {
    "description": "カメラに向かって話すクリップ（アイテムに依存しない）",
    "clips": [
      {"action": "looks at camera, talks, gestures", "cam": "A", "file": "talk_gesture.mp4"},
      {"action": "chin on hand, talks softly", "cam": "A", "file": "talk_chin.mp4"},
      {"action": "leans forward, excited telling", "cam": "A", "file": "talk_excited.mp4"},
      {"action": "looks away thinking, back to camera", "cam": "A", "file": "talk_think.mp4"},
      {"action": "laughs mid-sentence, waves hand", "cam": "A", "file": "talk_laugh.mp4"},
      {"action": "whispers like sharing a secret", "cam": "A", "file": "talk_whisper.mp4"}
    ]
  },

  "transitions": {
    "description": "場面転換クリップ",
    "clips": [
      {"action": "stands up from desk, walks to shelf", "cam": "C", "file": "trans_desk_shelf.mp4"},
      {"action": "walks from bed to desk", "cam": "C", "file": "trans_bed_desk.mp4"},
      {"action": "walks to window, looks out", "cam": "C", "file": "trans_window.mp4"},
      {"action": "sits down at desk from standing", "cam": "B", "file": "trans_sit.mp4"}
    ]
  }
}
```

### 話題 → アイテムのマッピング

```python
TOPIC_ITEMS = {
    '本':     ['bookshelf', 'desk', 'mug'],
    '宇宙':   ['telescope', 'desk', 'bookshelf'],
    '音楽':   ['guitar', 'headphones', 'desk'],
    '猫':     ['cat', 'bed', 'mug'],
    '勉強':   ['desk', 'bookshelf', 'mug'],
    '深夜':   ['desk', 'mug', 'headphones'],
    '夜':     ['bed', 'mug', 'plants'],
    '朝':     ['bed', 'desk', 'mug'],
    '花':     ['plants', 'desk'],
    '森':     ['plants', 'bookshelf'],
    'ゲーム': ['desk', 'headphones', 'mug'],
    '技術':   ['desk', 'bookshelf'],
    'AI':     ['desk', 'bookshelf'],
    '動画':   ['bed', 'headphones', 'mug'],
    '雨':     ['desk', 'mug', 'plants'],
    '食べ物': ['desk', 'mug'],
    '充電':   ['bed', 'desk'],
    '友達':   ['desk', 'mug', 'cat'],
    '旅':     ['desk', 'bookshelf', 'bed'],
    '夢':     ['bed', 'desk'],
    '体':     ['bed', 'desk', 'mug'],
    '寝る':   ['bed', 'cat'],
    '星':     ['telescope', 'mug', 'bed'],
    '海':     ['bookshelf', 'bed', 'desk'],
}
# デフォルト（マッチしない話題）: ['desk', 'mug']
```

### ランタイムクリップ選択（新規性の保証）

```
発話開始
  → talking クリップをランダム選択（前回と違うものを優先）
  → 10秒後、同じ話題の別アイテムクリップに切替
  → さらに10秒後、また別のアイテムorトーキングに切替
  → 使用済みクリップを記録し、全消化するまで再使用しない

1つの話題での流れ（例: 本の話、3分間）
  0:00  talk_gesture.mp4     (カメラ目線で話す)
  0:20  shelf_browse.mp4     (本棚から本を取り出す)
  0:40  talk_think.mp4       (考えながら話す)
  1:00  mug_sip.mp4          (お茶を飲む)
  1:20  shelf_read.mp4       (本を読む)
  1:40  talk_excited.mp4     (興奮して話す)
  2:00  trans_desk_shelf.mp4 (立って本棚に戻る)
  2:20  desk_typing.mp4      (ノートPCで何か調べる)
  2:40  talk_chin.mp4        (あごに手を当てて話す)

→ 3分間で9種類のクリップ。1つも繰り返さない。
```

### 新規性保証アルゴリズム

```python
class ClipPool:
    def __init__(self, item_ids: list):
        self.available = []  # 未使用クリップ
        self.used = []       # 使用済み
        self._load_clips(item_ids)
    
    def next(self, prefer_type=None) -> str:
        # 1. prefer_typeがあればそれを優先
        # 2. 未使用プールから選択
        # 3. 全消化したらリセット（シャッフル）
        candidates = self.available
        if prefer_type:
            typed = [c for c in candidates if c['cam'] == prefer_type]
            if typed: candidates = typed
        if not candidates:
            self.available = list(self.used)
            self.used = []
            random.shuffle(self.available)
            candidates = self.available
        clip = random.choice(candidates)
        self.available.remove(clip)
        self.used.append(clip)
        return clip['file']
```

### 部屋の一貫性（構造問題の解決）

**問題:** Flux AIは毎回部屋を「再発明」する。家具の位置が変わる。

**解決:** 部屋のレイアウトを厳密に記述し、プロンプトに常に含める。

```python
ROOM_LAYOUT = """
Room layout (MUST be consistent in every image):
- CAMERA: 3/4 view from lower-left corner, slight upward angle
- LEFT WALL: window with city night view, desk directly below it
- BACK WALL: tall bookshelf (center-left), fairy lights string along top
- RIGHT SIDE: bed with pillows (corner), door visible
- FLOOR: warm wooden boards
- DESK: laptop, small lamp, paw-print mug, headphones on lamp
- BY WINDOW: small telescope (right of desk)
- BY BOOKSHELF: guitar leaning against it
- NEAR BED: cat cushion with orange cat
- WINDOWSILL: small potted succulents
"""
```

**重要:** すべてのFlux画像は同じレイアウト記述を使う。
アイテムが増減した場合のみレイアウト記述を更新する。

### 部屋の進化（買ったり捨てたりする）

```python
# 新アイテム追加の例
room_state.add_item({
    'id': 'lava_lamp',
    'position': 'on desk, right side',
    'description': 'retro lava lamp with blue bubbles',
    'added': '2026-05-01',
    'clips': []  # プリレンダー後に追加
})

# ROOM_LAYOUT記述が自動更新される
# → 次のプリレンダーで新アイテムのクリップを生成
# → 配信で「新しいの買った」と話題にできる

# 古いアイテム引退の例
room_state.retire_item('telescope')
# → クリップは残るが新規生成しない
# → ROOM_LAYOUTから消える
# → 配信で「あの望遠鏡、友達にあげた」と言える
```

### コメント → アイテム連携

```python
# コメントからアイテムキーワードを検出
ITEM_KEYWORDS = {
    'cat': ['猫', 'ねこ', 'にゃん', 'みかん'],
    'guitar': ['ギター', '弾い', '音楽'],
    'telescope': ['望遠鏡', '星', '宇宙'],
    'bookshelf': ['本', '読', '小説'],
    'plants': ['植物', '緑', 'サボテン'],
    'mug': ['コーヒー', 'お茶', '飲み物'],
}

# コメントにアイテム名が含まれる → そのアイテムのクリップを即再生
# 例: 「猫かわいい！」→ cat_show.mp4（猫をカメラに見せる）
# 例: 「ギター弾いて」→ guitar_play.mp4（ギター演奏）
```

### 字幕の修正

**問題:** 字幕が全文表示されない
**原因の候補:**
1. テキストが長すぎてオーバーフロー
2. 【間】【長間】タグが字幕に含まれている
3. WebSocketメッセージが途中で切れている

**修正方針:**
- subtitle.htmlでテキストの最大幅・折り返しを確保
- 【間】【長間】タグを字幕表示前にstrip
- テキストが長い場合は自動的にフォントサイズを縮小

### プリレンダー予算

| カテゴリ | 本数 | 内容 |
|---------|------|------|
| furniture (3) x 4clips | 12 | desk, bookshelf, bed |
| items (6) x 4clips | 24 | guitar, telescope, cat, mug, headphones, plants |
| talking | 6 | カメラ目線バリエーション |
| transitions | 4 | 場所移動 |
| reactions | 6 | 感情（既存） |
| **合計** | **52本** | |

1本 = Flux($0.003) + Kling($0.13) = $0.133
52本 x $0.133 = **$6.92**（$10で余裕）

**話題あたりのクリップ数:**
- 3-4アイテム x 4clips = 12-16本
- + 6 talkingクリップ
- + 4 transitionクリップ
= **22-26本のプールから選択**

3分の話題 = 約9回のクリップ切替
→ **1回も繰り返さずに3分間持つ**

## 実装優先順

### Phase 1: 即時修正（バグ）
1. 字幕全文表示の修正
2. ClipSelectorが実際にクリップを切り替える確認

### Phase 2: データモデル
1. `room_state.json` 作成（部屋レイアウト + アイテム定義）
2. `ROOM_LAYOUT` 定数（一貫した部屋記述）
3. `TOPIC_ITEMS` マッピング
4. `ITEM_KEYWORDS` コメント検出

### Phase 3: プリレンダー刷新
1. image_generator.pyをアイテムベースに書き換え
2. prerender.pyをアイテム単位に変更
3. 52本のクリップをプリレンダー

### Phase 4: ランタイム
1. ClipPool（新規性保証アルゴリズム）
2. コメント→アイテム検出→クリップ切替
3. 10秒ごとの自動クリップ切替
4. トランジションクリップの挿入

### Phase 5: 部屋進化
1. アイテム追加/引退のAPI
2. ROOM_LAYOUTの動的生成
3. 配信中にまおが新アイテムについて話す
