<div align="center">

# 🌙 distributed-ai-idol

**自律型AI VTuber配信システム ── まおが自分で考えて、自分で話す**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

[日本語](#概要) | [English](#overview)

</div>

---

## 概要

AIキャラクター「まお」がYouTubeで自律的にライブ配信を行うシステムです。
人間は配信を開始するだけ。話題選択、感情表現、音声合成、映像生成まで全てAIが自律的に行います。

**デモ:** [YouTube 初回配信アーカイブ](https://youtube.com/live/XKmC0gpTC04)

### ✨ 特徴

- 🧠 **神経科学ベースの感情システム** ── LeDoux(1996)の扁桃体バイパス理論に基づく4段階処理
- 🎭 **Big Five性格モデル** ── Costa & McCrae(1992)に基づく一貫した性格表現
- 🎬 **AI映像パイプライン** ── Flux画像生成 + Kling動画生成のピンポンループ
- 🗣️ **日本語音声合成** ── AivisSpeechによる自然な日本語発話
- 💬 **自律的会話生成** ── Claude APIによる話題展開・感情連動
- 🐱 **「まおの部屋」ドキュメンタリー** ── 部屋で暮らすAIの配信コンセプト


## アーキテクチャ

```
入力（コメント / 自律思考）
  ↓
┌─────────────────────────────────────┐
│ Stage 1: 反射層 (<20ms, ルールベース)  │  ← LeDoux 扁桃体バイパス
│   驚き・防衛・親密さの即時反応         │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│ Stage 2: 感情評価 (Claude API)       │  ← 前頭前野モデル
│   感情を出すか・抑えるかの判断         │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│ Stage 3: 表現生成 (Claude API)       │  ← 言語野モデル
│   Big Five性格に基づく発話生成         │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│ Stage 4: 記憶保存 (Zep Cloud)        │  ← 海馬モデル
│   エピソード記憶・関係性グラフ          │
└─────────────────────────────────────┘
               ↓
      音声合成 → 映像選択 → OBS配信
```

## 映像パイプライン

| レイヤー | 技術 | 説明 |
|---------|------|------|
| 背景 | HTML Canvas | オーロラ+パーティクルアニメーション |
| 映像 | Flux + Kling | 51クリップのKling動画ピンポンループ |
| 字幕 | WebSocket | リアルタイム字幕表示 |

- **ホームショット**: talkingクリップ動画が常駐（5秒→逆再生→ループ）
- **カットアウェイ**: 【長間】で小道具・家具クリップに一時切替
- **Living Portrait**: 動画なしの場合は瞬き・呼吸・髪揺れアニメーション


## 技術スタック

| コンポーネント | 技術 | 用途 |
|------------|------|------|
| LLMブレイン | Claude API (Anthropic) | 会話生成・感情評価 |
| 音声合成 | AivisSpeech | 日本語音声合成（OSS） |
| 画像生成 | Flux [schnell] (PiAPI) | キャラクター画像（Apache 2.0） |
| 動画生成 | Kling (PiAPI) | 5秒動画クリップ |
| 記憶層 | Zep Cloud | ナレッジグラフ・エピソード記憶 |
| 設定管理 | Firestore | 3層設定（DB→JSON→.env） |
| 音声出力 | VB-CABLE | 仮想オーディオデバイス |
| 配信 | OBS Studio | YouTube Live配信 |

## セットアップ

### 前提条件
- Windows 10/11 64bit
- Python 3.12+
- OBS Studio
- AivisSpeech
- VB-CABLE

### インストール

```bash
git clone https://github.com/kokimi28/distributed-ai-idol.git
cd distributed-ai-idol
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env  # APIキーを設定
```

### 起動

```bash
# 1. AivisSpeechを起動
# 2. OBSを起動（ブラウザソース3つ設定）
python run_broadcast.py --duration 30
# 3. OBSブラウザソースのキャッシュをクリア
```


## プロジェクト構造

```
distributed-ai-idol/
├── brain/              # 話題エンジン・反射層・感情処理
│   ├── topic_engine.py     # 話題ライフサイクル管理
│   ├── topic_generator.py  # Claude APIで話題生成
│   ├── reflex_layer.py     # Stage 1: 感情反射
│   └── stream_clock.py     # 配信フェーズ管理
├── broadcast/          # 配信パイプライン
│   ├── pipeline.py         # メイン配信ループ
│   └── overlay_server.py   # WebSocket + HTTPサーバー
├── llm/                # Claude API連携
│   └── claude_bridge.py    # LLM生成インターフェース
├── memory/             # 記憶システム
│   ├── zep_client.py       # Zep Cloud連携
│   └── emotion_carry.py    # 感情の残り香モデル
├── overlay/            # ブラウザオーバーレイ
│   ├── main_visual.html    # Kling動画プレイヤー
│   ├── subtitle.html       # 字幕表示
│   └── aurora.html         # オーロラ背景
├── video/              # 映像パイプライン
│   ├── clip_selector.py    # ホームショット管理
│   ├── image_generator.py  # Flux画像生成
│   ├── video_generator.py  # Kling動画生成
│   └── prerender.py        # 51クリップ一括生成
├── voice/              # 音声処理
│   └── aivisspeech.py      # AivisSpeech連携
├── character/          # キャラクター設定
│   └── big_five.py         # Big Five性格プロファイル
├── shared/             # 共通ユーティリティ
│   └── config_store.py     # Firestore設定管理
└── docs/               # 設計書・手順書
```

## コントリビューション

プルリクエスト歓迎です！以下の領域で特に貢献を求めています：

- 🎨 **映像品質向上** ── 新しいクリップ・カメラアングル・表情バリエーション
- 🧠 **会話品質改善** ── トピックエンジンの深化・脱線ロジック
- 🌐 **多言語対応** ── 英語・中国語等での配信サポート
- 📊 **分析ダッシュボード** ── 配信メトリクス・感情推移の可視化
- 🎵 **BGM・SE** ── 雰囲気に合った音響デザイン
- 📱 **モバイル対応** ── スマホからの配信制御


## 設計思想

このプロジェクトは「AIキャラクターを科学的に設計する」ことを目指しています。
v4設計書では以下の研究に基づいてまおの「脳」を構築しました：

| 研究 | 適用 |
|------|------|
| LeDoux (1996) 扁桃体バイパス | 反射層（Stage 1）|
| Kahneman (2011) 二重過程理論 | 4段処理フロー |
| Costa & McCrae (1992) Big Five | 性格プロファイル |
| Isen (1984) 感情持続効果 | 感情の残り香モデル |
| Bachnick (1992) uchi-soto | 配信/個人モード分離 |

詳細は `docs/分散AIアイドル_科学的整合性検証_設計v4.docx` を参照。

---

## Overview (English)

An autonomous AI VTuber livestreaming system. The AI character "Mao" independently thinks, speaks, and broadcasts on YouTube without human intervention.

**Key Features:**
- Neuroscience-based emotion system (4-stage processing pipeline)
- Big Five personality model for consistent character expression
- AI-generated visuals (Flux + Kling video pipeline)
- Japanese voice synthesis (AivisSpeech)
- Autonomous conversation generation (Claude API)
- Memory persistence (Zep Cloud knowledge graph)

---

## ライセンス

MIT License - 詳細は [LICENSE](LICENSE) を参照。

## 謝辞

- [Anthropic](https://anthropic.com/) - Claude API
- [AivisSpeech](https://aivis-project.com/) - 日本語音声合成
- [Black Forest Labs](https://bfl.ai/) - Flux画像生成
- [PiAPI](https://piapi.ai/) - Flux/Kling API
- [Zep](https://getzep.com/) - メモリレイヤー

