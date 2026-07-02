#!/usr/bin/env bash
# takt runtime.prepare スクリプト
# ------------------------------------------------------------------
# git-worktree 内で mise(Python 3.12 + uv)を用意し、uv で依存を同期する。
#
# 仕様(takt runtime-environment):
#   - このスクリプトはワークツリーを cwd として `bash` で実行される。
#   - 標準出力(stdout)に出した `KEY=VALUE` 行だけがエージェントの環境変数へ
#     注入される(前後の引用符は1組ぶん除去される / 値は変数展開されない)。
#   - それ以外のログは必ず標準エラー(stderr, `1>&2`)へ出すこと。
#   - PATH は展開されないため、mise env の「解決済み」値をそのまま渡す。
# ------------------------------------------------------------------
set -euo pipefail

log() { echo "[prepare-python] $*" 1>&2; }

# --- 大きなキャッシュ(torch wheel / DINOv3 重み)はワークツリー間で共有し再DLを避ける ---
export UV_CACHE_DIR="${UV_CACHE_DIR:-$HOME/.cache/uv}"
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"   # transformers / hub 重み
export TORCH_HOME="${TORCH_HOME:-$HOME/.cache/torch}"    # torch.hub (DINOv3) 重み
mkdir -p "$UV_CACHE_DIR" "$HF_HOME" "$TORCH_HOME"

# --- mise で python/uv を用意(mise.toml をトラスト)---
if ! command -v mise >/dev/null 2>&1; then
  log "ERROR: mise が PATH に見つかりません。mise を有効化してから実行してください。"
  exit 1
fi
log "mise trust & install ..."
mise trust --quiet "$PWD" 1>&2 || true
mise install 1>&2

# --- uv で依存を同期(.venv 作成 + cu130 torch / DINOv3対応 anomalib / LLM/dev)---
# 開発ワークツリー想定で llm + dev extra を入れる(pytest / ruff / onnx 等)。
# 軽量にしたい場合は `--extra dev` を外す。
log "uv sync (--extra llm --extra dev) ..."
mise exec -- uv sync --extra llm --extra dev 1>&2

# --- エージェントへ注入する環境変数を stdout へ出力 ---
# mise env が解決済みの PATH と VIRTUAL_ENV(.venv 有効化)を含む
mise env --shell bash | sed 's/^export //'
# 共有キャッシュ位置も後続コマンドへ引き継ぐ
echo "UV_CACHE_DIR=$UV_CACHE_DIR"
echo "HF_HOME=$HF_HOME"
echo "TORCH_HOME=$TORCH_HOME"

log "done."
