# Kling AI 動画生成 セットアップガイド

## 概要

配信中に話題に連動するアニメ風AI動画を背景に表示する機能。
PiAPI経由でKling AIのAPIを使う。

---

## STEP 1: PiAPIアカウント作成

1. https://piapi.ai/ にアクセス
2. 右上の「Get Started」または「Sign Up」をクリック
3. Googleアカウント or メールアドレスで登録
4. メール認証が来たら確認リンクをクリック

> 登録するとFREE Playgroundクレジットが付与される（テスト用）

---

## STEP 2: APIキーの取得

1. ログイン後、https://app.piapi.ai/ にアクセス（Workspace画面）
2. 左メニューの「API Keys」をクリック
3. 「Create New Key」ボタンをクリック
4. キー名を入力（例: `distributed-ai-idol`）
5. 表示されたAPIキーをコピー

> ⚠ APIキーは一度しか表示されない。必ずコピーして安全な場所に保存すること。

---

## STEP 3: .envファイルに設定

プロジェクトの `.env` ファイルを開いて、以下を更新:

```
# ===== Kling AI Video =====
KLING_API_KEY=ここにコピーしたAPIキーを貼り付け
KLING_PROVIDER=piapi
```

> `xxxxxxxx...` のプレースホルダーを実際のキーに置き換える

---

## STEP 4: 動作確認

PowerShellで以下を実行:

```powershell
cd C:\Projects\distributed-ai-idol
.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "C:\Projects\distributed-ai-idol"
python -c "from video.video_generator import VideoGenerator; vg=VideoGenerator(); print('enabled:', vg.is_enabled)"
```

`enabled: True` と表示されればOK。

---

## STEP 5: テスト生成（単体）

APIが正しく動作するかテスト:

```powershell
python -c "
import asyncio
from video.video_generator import VideoGenerator, build_video_prompt
async def test():
    vg = VideoGenerator()
    print('enabled:', vg.is_enabled)
    prompt = build_video_prompt('宇宙の話', ['星', '銀河'])
    print('prompt:', prompt[:80])
    # 実際にAPI呼び出し（クレジットを消費する）
    task_id = await vg.provider.create_task(prompt, duration=5)
    print('task_id:', task_id)
    if task_id:
        print('タスク作成成功。ポーリング開始...')
        for i in range(30):
            await asyncio.sleep(10)
            status, url = await vg.provider.poll_status(task_id)
            print(f'  [{i*10}s] status={status}')
            if status == 'ready':
                print(f'  動画URL: {url}')
                local = await vg.provider.download_video(url, 'test_video.mp4')
                print(f'  保存先: {local}')
                break
            elif status == 'error':
                print('  エラー発生')
                break
asyncio.run(test())
"
```

> 生成には60-90秒かかる。`status=ready`になれば成功。
> 動画は `video/cache/test_video.mp4` に保存される。

---

## STEP 6: OBS Browser Sourceの設定

### 全画面背景モード
1. OBS → ソース → 「+」→ ブラウザ
2. 名前: `AI Video BG`
3. URL: `file:///C:/Projects/distributed-ai-idol/overlay/video_bg.html`
4. 幅: `1920` / 高さ: `1080`
5. ソースの順番: **一番下**（アンビエント背景の上、VTube Studioの下）

### モクモク雲モード（画面の一部に表示）
1. OBS → ソース → 「+」→ ブラウザ
2. 名前: `AI Video Cloud`
3. URL: `file:///C:/Projects/distributed-ai-idol/overlay/video_bg.html?mode=cloud`
4. 幅: `1920` / 高さ: `1080`
5. ソースの順番: VTube Studioの下

> 両方追加して、シーンごとに使い分けることも可能

---

## 料金目安

PiAPIのKling API（pay-as-you-go）:
- Standard 5秒動画: 約$0.14/本
- Standard 10秒動画: 約$0.28/本
- 1時間配信（10-15話題）: 約$1.4〜$4.2

月額プランもあり（$9.99〜でクレジット付与）。
詳細: https://piapi.ai/pricing

---

## 代替プロバイダ

PiAPI以外にも対応済み。`.env`の`KLING_PROVIDER`を変更するだけ:

| プロバイダ | KLING_PROVIDER値 | 特徴 |
|-----------|-----------------|------|
| PiAPI | `piapi` | 推奨。Playground付き。複数モデル統合 |
| AIML API | `aimlapi` | 複数AIモデル統合プラットフォーム |
| Kling公式 | `kling_official` | 直接API。klingai.com で取得 |

---

## トラブルシューティング

### `enabled: False` と表示される
- `.env`の`KLING_API_KEY`がプレースホルダー(`xxxxxx...`)のまま
- `.env`ファイルを保存した後、PowerShellを再起動する

### タスク作成時にエラー
- APIキーが無効 → PiAPIダッシュボードで確認
- クレジット残高不足 → PiAPIでトップアップ
- レートリミット → 数秒待って再試行

### 動画が表示されない
- OBS Browser Sourceの「ページ権限」→「ローカルファイルへのアクセス」を有効にする
- WebSocket接続確認: ブラウザコンソール（F12）で`WS connected`が出ているか
- `python run_broadcast.py`が起動していてOverlayServerが動いているか

### 動画の品質が低い
- `mode`を`std`→`pro`に変更（コスト2倍だが品質向上）
- `video_generator.py`の`create_task`で`mode='pro'`に変更
