# CLAUDE.md — distributed-ai-idol

自律型 AI VTuber 配信システム「まお」。YouTube で AI が自律的にライブ配信する **Python モノリス**（話題選択・感情表現・音声合成・映像生成まで自走）。人間は配信を開始するだけ。

> 標準適用の第一歩（dev-env G9 / Issue #4）。本 CLAUDE.md はリポの構成・検証・秘密の扱いをエージェントが把握するための正本。CI は #4 の続きで整備する（後述の「検証」の注記参照）。

## エントリポイント

```
python run_broadcast.py                 # 通常起動（YouTube Chat 自動検出）
python run_broadcast.py --no-youtube    # YouTube Chat なし（ローカルテスト）
python run_broadcast.py --chat-id=XXXXX # liveChatId 直接指定
python run_broadcast.py --duration=30   # 30分配信
```

Python **3.12+**（本開発機は 3.13/3.14）。依存は `requirements.txt`（`pip install -r requirements.txt`）。

## ディレクトリ構成

| ディレクトリ | 役割 |
|---|---|
| `brain/` | 話題エンジン（topic engine・phase 管理） |
| `character/` | 性格・人格（Big Five モデル `big_five.py` 等） |
| `llm/` | Claude API による会話・感情連動生成 |
| `voice/` | 日本語音声合成（AivisSpeech / ElevenLabs） |
| `video/` | AI 映像パイプライン（Flux 画像 + Kling 動画のピンポンループ） |
| `overlay/` | 配信オーバーレイ（VTube 連携・表情） |
| `broadcast/` | YouTube 配信・ライブチャット取り込み |
| `memory/` | 記憶（Zep） |
| `shared/` | 共通設定 `config_store.py` 等（多くのモジュールがここを import） |
| `logs/` | 実行ログ |
| `docs/` | 設計・引継ぎ資料 |
| `tests/` | テスト＋開発用スクリプト（下記の注意） |

## 検証（テスト）

**現状、`tests/` は「純ロジックのユニットテスト」と「実機・キー・ネットワーク依存のスクリプト」が混在**している（`test_*` 命名だが pytest 前提でないものも多い）。CI で全体を回すには仕分けが要る（Issue #4 の続きタスク）:

- **純ロジック系（CI 候補）**: `test_config_store` / `test_big_five` / `test_emotion_carry` / `test_emotion_voice` / `test_develop_variety` / `test_autonomous_talk` / `test_text_parser` / `test_smart_picker` / `test_stream_clock` / `test_reflex` / `test_topic_engine` / `test_duration` 等。
- **実機・キー・ネットワーク依存（CI 除外）**: `integration/*`（AivisSpeech / VB-Cable / VTube / full pipeline）、`test_youtube_*` / `test_elevenlabs` / `test_kling_debug` / `test_video_api_live` / `test_image_*` / `test_zep_client`、および `gen_*` / `debug_*` / `preflight` / `migrate_*` などの開発スクリプト。
- **CI 化の既知ブロッカー**: ① `pyaudio` は PortAudio のシステムライブラリが要る（Ubuntu ランナーでは `apt-get install -y portaudio19-dev` を先に）。② 純ロジック系も `shared.config_store` 経由で `loguru` / `python-dotenv` 等を import するため、**`requirements.txt` の一括インストールが前提**（サブセットだけの軽量実行は不可）。③ 実機・キー依存を確実に外すため **pytest marker（例: `@pytest.mark.live` / `hardware`）での仕分け**が必要。

推奨の到達形: marker を付与し、CI は `pytest -m "not (live or hardware)"` で純ロジックのみ green にする（キー投入＝#1 env-bootstrap とは独立）。

ローカルで純ロジックを試すには（要フル依存インストール）:
```
pip install -r requirements.txt pytest
pytest tests/test_config_store.py tests/test_big_five.py -q
```

## secrets（値に触れない）

- **キーの値はコード・コミット・Issue・PR・ログに一切書かない**（扱うのはキー名のみ）。正本は claude-ops の GOVERNANCE.md。
- 各サービスのキー（Claude / YouTube (google-api) / ElevenLabs / Firebase (firebase-admin) / Zep / Stripe / Discord 等）は env（`.env`）経由で注入。**投入は 👤 専任**（初期シークレット投入＝人間の接点）。
- `.env` は gitignore 済み。読み取り・コミットしない。新しい env を足すときはキー名だけを例示ファイルに追記（値は空）。

## 現況

- **env-bootstrap 進行中**（Issue #1・ブランチ `env-bootstrap`）: コールドスタート→配信可能 の再現・キー投入待ち。手順は `docs/bootstrap.md`。
- **標準適用中**（Issue #4）: 本 CLAUDE.md が第一歩。CI（純ロジック pytest）は marker 整備後に追加。
- 命名は旧「distributed」構想の名残だが実態は単機のモノリシック配信アプリ（dev-env の命名規約対象外・改名しない）。
