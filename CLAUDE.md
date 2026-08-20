# CLAUDE.md — distributed-ai-idol

自律型 AI VTuber 配信システム「まお」。YouTube で AI が自律的にライブ配信する **Python モノリス**（話題選択・感情表現・音声合成・映像生成まで自走）。人間は配信を開始するだけ。

> 標準適用（dev-env G9 / Issue #4）の正本。本 CLAUDE.md はリポの構成・検証・秘密の扱いをエージェントが把握するためのもの。CI は導入済み（後述の「検証」節）。

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
**CI（unit ティア・`.github/workflows/ci.yml`・2026-07-19 導入）**: 純ロジックテストだけを green にする。ポイント:
- 純ロジックの実行に要るのは**軽量依存 `loguru` / `python-dotenv` / `pydantic`（＋`pytest`）のみ**。フル依存（`requirements.txt` の `pyaudio`→PortAudio・firebase・grpc 等）は不要。
- pytest はマーカ選択でも**全テストを import 収集**するため、フル依存が無いと収集段階で実機・キー依存テストが ImportError になる。そこで CI は**検証済みの純ロジックテストを明示列挙**して収集対象を限定する（marker 方式は採らない）。新しい純ロジックテストを足したら ci.yml のリストに追記する。
- 現在の CI 対象（実測 green・2026-07-19）: `test_text_parser` / `test_stream_clock` / `test_smart_picker` / `test_emotion_carry` / `test_emotion_voice` / `test_big_five` / `test_reflex` / `test_develop_variety`。
- **実機・キー・ネットワーク依存**（youtube / elevenlabs / kling / video / image / vtube / aivispeech / zep / firebase / LLM 等）は CI 対象外。キー投入（#1）と実機が要る「フル/live ティア」は別途。

ローカルで unit ティアを再現:
```
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install loguru python-dotenv pydantic pytest
pytest tests/test_text_parser.py tests/test_big_five.py -q   # 等、上のリスト
```

## secrets（値に触れない）

- **キーの値はコード・コミット・Issue・PR・ログに一切書かない**（扱うのはキー名のみ）。正本は claude-ops の GOVERNANCE.md。
- 各サービスのキー（Claude / YouTube (google-api) / ElevenLabs / Firebase (firebase-admin) / Zep / Stripe / Discord 等）は env（`.env`）経由で注入。**投入は 👤 専任**（初期シークレット投入＝人間の接点）。
- `.env` は gitignore 済み。読み取り・コミットしない。新しい env を足すときはキー名だけを例示ファイルに追記（値は空）。

## 現況

- **env-bootstrap 進行中**（Issue #1・ブランチ `env-bootstrap`）: コールドスタート→配信可能 の再現・キー投入待ち。手順は `docs/bootstrap.md`。
- **標準適用は完了**（Issue #4・2026-07-18 `fd15349`）: 本 CLAUDE.md ＋ CI（純ロジック pytest・`.github/workflows/ci.yml`）が入り、master で green を実測済み。dev-env の適用基準では dormant リポの標準は **CLAUDE.md のみが最小**（`template-adoption-guide.md` §適用優先度）なので、CI がある本リポは基準を満たしている。**marker 方式は採らなかった**（上の「検証」節の理由＝pytest はマーカ選択でも全テストを import 収集するため、フル依存が無いと収集段階で落ちる）。
- 命名は旧「distributed」構想の名残だが実態は単機のモノリシック配信アプリ（dev-env の命名規約対象外・改名しない）。
