#!/usr/bin/env python3
"""SessionStart hook — リモート（claude.ai/code クラウド）セッションの準備＋環境自己診断（preflight）。

ローカル実行では何もしない（即 exit 0）。クロスプラットフォーム（stdlib のみ）。
ベストエフォート: 失敗してもセッションを止めない（常に exit 0）。
stdout はセッション冒頭のコンテキストに注入される。

本リポの依存導入は CLAUDE.md「ローカルで unit ティアを再現」と同一の軽量依存4つのみ
（loguru / python-dotenv / pydantic / pytest）。requirements.txt のフル依存は入れない。
"""

import os
import shutil
import subprocess
import sys


def run(cmd: list[str], timeout: int = 540) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        tail = (p.stderr or "").strip().splitlines()
        return p.returncode, tail[-1] if tail else ""
    except Exception as e:  # noqa: BLE001 — ベストエフォート
        return 1, str(e)


def setup_dependencies(project_dir: str) -> str:
    """unit ティアの軽量依存を uv で導入（冪等・uv.lock は作らない）。"""
    if not os.path.isdir(os.path.join(project_dir, ".venv")):
        code, err = run(["uv", "venv", "--python", "3.12", ".venv"], timeout=120)
        if code != 0:
            return f"uv venv 失敗（{err}）"
    venv_python = ".venv/bin/python" if os.name != "nt" else ".venv\\Scripts\\python.exe"
    code, err = run(
        ["uv", "pip", "install", "loguru", "python-dotenv", "pydantic", "pytest", "--python", venv_python],
        timeout=480,
    )
    if code != 0:
        return f"uv pip install 失敗（{err}）"
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        venv_bin = os.path.join(project_dir, ".venv", "bin")
        with open(env_file, "a", encoding="utf-8") as f:
            f.write(f'export PATH="{venv_bin}:$PATH"\n')
    return "uv venv + 軽量依存4つ（loguru / python-dotenv / pydantic / pytest）導入済（.venv/bin を PATH 注入）"


def main() -> int:
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return 0
    try:
        return _main_remote()
    except Exception as e:  # noqa: BLE001 — hook はセッションを止めない
        print(f"[remote-preflight] 診断失敗（{e}）。手動で依存導入・環境確認をすること。")
        return 0


def _main_remote() -> int:
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    os.chdir(project_dir)

    deps = setup_dependencies(project_dir)

    def have(bin_name: str) -> str:
        return "あり" if shutil.which(bin_name) else "なし"

    print(
        f"""[remote-preflight] クラウドコンテナ（Linux）で実行中。環境診断:
- 依存: {deps} / python3 {sys.version.split()[0]}（システム。unit ティアは .venv の 3.12 を使う）
- uv: {have("uv")} / ffmpeg: {have("ffmpeg")}
この環境での動き方（CLAUDE.md「リモート/クラウドセッション運用」節が正）:
- 検証は unit ティア（.github/workflows/ci.yml と同一の純ロジックテスト列挙）を .venv/bin/pytest で必ず実行。
- 実機・キー・ネットワーク依存（youtube / elevenlabs / kling / vtube / aivispeech / zep / firebase / LLM 等）は実行不可 → PR の「未検証項目」に列挙し、それを理由に停止しない。
- secrets（.env）はこの環境に無い（値の要求・推測・生成をしない）。純ロジックテストを追加したら ci.yml のリストに追記する。"""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
