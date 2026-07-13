# bootstrap.md — コールドスタート → 配信可能

fresh clone から「配信可能」状態までの**再現手順（1枚集約版）**。
本書は **コード / `requirements.txt` を正**として作成し、実機（Windows 11）で検証した。
古いドキュメント（`引継ぎ書_*` 等）との差異は末尾「付録A: ドキュメント↔コード差異」に列挙する。

> 検証環境: `C:\Users\kokim\github\distributed-ai-idol` / Python 3.13.14 / 2026-07-13
> 検証範囲: venv・依存導入・オフラインテスト・import/初期化まで（外部GUI・実APIキーを要する経路は 👤 の後）

---

## 0. 前提（ソフトウェア）

| 種別 | 要件 | 備考 |
|------|------|------|
| OS | Windows 10/11 64bit | |
| Python | **3.12+**（badge準拠） | 実機に3.12は無く **3.13.14 で検証OK**。`pyaudio` は cp313 prebuilt wheel が入りビルド不要 |
| OBS Studio | 最新 | ブラウザソース3つ（下記ポート） |
| AivisSpeech | 最新 | `--cors_policy_mode all` で起動（👤） |
| VB-CABLE | 仮想オーディオ | AivisSpeech音声→OBS |
| VTube Studio / VSeeFace | 任意 | 表情連動。無くても `--no-vtube` で配信可 |

---

## 1. リポジトリ取得 → venv → 依存導入（✅検証済み）

```powershell
cd C:\Users\kokim\github
git clone https://github.com/kokimi28/distributed-ai-idol.git
cd distributed-ai-idol

# 3.12 が無い環境では 3.12+ を満たす既存版を指定（本検証は 3.13）
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt   # 実機で exit 0（エラー/警告なし）
```

- 依存15本＋推移的依存が正常導入。`pyaudio 0.2.14`・`grpcio`・`firebase-admin` 等もwheelで解決。
- 日本語ログが文字化けする場合は `$env:PYTHONUTF8 = "1"`（または `chcp 65001`）。

---

## 2. `.env` 準備（値の投入は 👤）

`.env.example` を雛形に `.env` を作る。**secretの値はオーナーが投入**（本リポジトリはggshield運用・`.env`はgitignore済み）。

```powershell
Copy-Item .env.example .env   # その後、値を埋める
```

### 実際にコードが読むキー（`os.getenv` 準拠）

| キー | 必須/任意 | 用途 | 未設定時の挙動 |
|------|----------|------|----------------|
| `ANTHROPIC_API_KEY` | **必須** | 会話・感情・話題生成（Claude） | `ClaudeBridge` 構築時に例外 → 配信不可 |
| `CLAUDE_MODEL` | 任意 | モデルID上書き | 既定 `claude-sonnet-4-6` |
| `KLING_API_KEY` | 任意 | Flux画像/Kling動画（PiAPI） | 画像/動画生成OFF（`is_enabled=False`）でも配信は継続 |
| `KLING_PROVIDER` | 任意 | `piapi`/`aimlapi`/`kling_official` | 既定 `piapi` |
| `ZEP_API_KEY` | 任意 | エピソード記憶（Zep Cloud） | 記憶OFFで継続 |
| `FIREBASE_CREDENTIALS_PATH` | 任意 | Firestore設定層 | 未接続なら `shared/seed_data.json` にフォールバック（✅検証済み） |
| `YOUTUBE_API_KEY` / `YOUTUBE_CHANNEL_ID` | 任意 | コメント取得 | `--no-youtube` 相当。無しでも自律発話 |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` / `ELEVENLABS_MODEL_BROADCAST` | 任意 | 代替音声エンジン | `--engine elevenlabs` 使用時のみ必要。既定は AivisSpeech |
| `AIVIS_STYLE_*`（6種）/ `REFLEX_SILENCE_MINUTES_THRESHOLD` | 任意 | 微調整 | すべてコード側に既定値あり |

> ⚠ `.env.example` にある `AIVISSPEECH_URL` / `AIVISSPEECH_SPEAKER_ID` / `CHARACTER_NAME` / `CHARACTER_MODE` / `FIREBASE_PROJECT_ID` は**現行コードでは未参照**（付録A-4参照）。AivisSpeechのURLは `voice/synthesizer.py` が `http://127.0.0.1:10101` を直書き。

---

## 3. 外部サービス / GUI 準備（👤 オーナー作業）

1. **Firebase**: プロジェクト作成 → service account JSON を `firebase-service-account.json` としてリポジトリ直下へ配置（gitignore済み）。※未配置でもJSONシードで起動可。
2. **AivisSpeech**: `--cors_policy_mode all` 付きで起動。
   ```powershell
   & "C:\Users\kokim\AppData\Local\Programs\AivisSpeech\AivisSpeech-Engine\run.exe" --cors_policy_mode all
   ```
   → `http://127.0.0.1:10101/speakers` が返れば疎通OK。
3. **OBS ブラウザソース3枚**（下→上）:
   | 層 | URL |
   |----|-----|
   | 背景 | `http://127.0.0.1:8766/overlay/aurora.html` |
   | 映像 | `http://127.0.0.1:8766/overlay/main_visual.html` |
   | 字幕 | `http://127.0.0.1:8766/overlay/subtitle.html` |
   起動後、3枚とも右クリック→「キャッシュクリア→ページ再読み込み」。
4. **VB-CABLE**: OBS マイク入力を `CABLE Output (VB-Audio Virtual Cable)` に。
5. **PiAPI**: frozen quota 時は Discord 経由で解放（👤）。
6. **各APIキー発行・課金**: Anthropic / PiAPI / Zep / YouTube /（任意）ElevenLabs。

---

## 4. 検証ラダー（下から順に確認）

| 段 | コマンド | 必要なもの | 本検証結果 |
|----|----------|-----------|-----------|
| ① オフライン単体 | `python -m tests.test_reflex` / `test_emotion_carry` / `test_big_five` | なし | ✅ 3件PASS（exit 0） |
| ② import/初期化 | 全モジュールimport＋`config.preload`＋`OverlayServer()`＋`VoicePipeline`＋pipeline構築 | なし | ✅ 25/25 OK |
| ③ プリフライト | `python tests\preflight.py` | 実キー＋AivisSpeech起動 | 👤（キー投入後）※付録A-5の注意 |
| ④ ローカル配信 | `python run_broadcast.py --no-youtube --no-vtube --duration 1` | ANTHROPIC_API_KEY | 👤 |
| ⑤ 本番配信 | `python run_broadcast.py --duration 30` | 全サービス＋OBS/GUI | 👤 |

- テスト①②は cwd=リポジトリ直下で実行（`-m` 実行 or `PYTHONPATH=.`）。
- `run_broadcast.py` 主要フラグ: `--duration`（分, 既定60）/ `--no-youtube` / `--no-vtube` / `--chat-id` / `--engine {aivispeech,elevenlabs}`。

### ポート早見

| 用途 | ポート |
|------|-------|
| Overlay WebSocket | `ws://127.0.0.1:8765` |
| Overlay HTTP（静的配信） | `http://127.0.0.1:8766` |
| AivisSpeech | `http://127.0.0.1:10101` |

---

## 付録A: ドキュメント↔コード差異（コードを正とする）

1. **モデル名**: コードは全箇所 `claude-sonnet-4-6`（`llm/claude_bridge.py:205`, `llm/claude_client_v4.py:45,75`, `brain/topic_generator.py:43`, `tests/preflight.py:53`, `.env.example`）。
   旧引継ぎ書 `引継ぎ書_20260323_v2.md:142` / `docs/引継ぎ書_20260325.md:141` は `claude-sonnet-4-5` のまま（20260414/20260415で 4-5→4-6 へ移行済み）。
   - ⚠ 実行前に `claude-sonnet-4-6` が現行Anthropic APIで有効なIDか要確認。404時は**コード変更不要**で `CLAUDE_MODEL` 環境変数で上書き可。
2. **音声エンジン**: `README.md` は AivisSpeech のみ記載だが、コードは **AivisSpeech（既定）＋ ElevenLabs** の2エンジン（`run_broadcast.py --engine`, `voice/synthesizer.py` の `VoicePipeline`, `tests/test_elevenlabs.py`）。READMEはElevenLabsをフォールバックとして未記載。
3. **`.env.example` に不足しているキー**（コードは参照）: `KLING_PROVIDER`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_BROADCAST`, `AIVIS_STYLE_*`, `REFLEX_SILENCE_MINUTES_THRESHOLD`。
4. **`.env.example` にあるが未参照のキー**: `AIVISSPEECH_URL`, `AIVISSPEECH_SPEAKER_ID`, `CHARACTER_NAME`, `CHARACTER_MODE`, `FIREBASE_PROJECT_ID`（`os.getenv` に出現せず）。
5. **パスの陳腐化**: `docs/kling_setup_guide.md`・`docs/OBS設定ガイド.md`・旧引継ぎ書、および **`tests/preflight.py:92`** が `C:\Projects\distributed-ai-idol` を直書き。実クローンパスは `C:\Users\kokim\github\distributed-ai-idol`。このため preflight の overlay ファイル存在チェック（`[6/6]`）は実パスで**誤って missing 判定**になる（推奨: `Path(__file__).parent.parent` 基準の相対化。※コード変更はオーナー判断）。
6. **requirements の残骸疑い**: `stripe>=10.0.0` / `discord.py>=2.4.0` を宣言するが、現行ツリーに `STRIPE_*`/`DISCORD_*` の `os.getenv` も `bot/discord_bot.py` も無い（discord_bot は最古 `引継ぎ書_20260323` のみ言及）。**配信ブートストラップにStripe/Discord-botキーは不要**。※👤リストの「PiAPI Discord」はPiAPIのサポート窓口で discord.py とは無関係。

## 付録B: 検証で確認した挙動（キー不要）

- `shared/config_store.py`: Firestore未初期化時、警告を出しつつ `shared/seed_data.json` の8キーを正常プリロード（グレースフル・デグレード）。
- `video/image_generator.py`・`video/video_generator.py`: キー未設定で `is_enabled=False`（例外を投げず配信継続）。
- `broadcast/overlay_server.py`: 構築時に ws=8765 / http=8766 を保持（bindは `start()` 時）。
