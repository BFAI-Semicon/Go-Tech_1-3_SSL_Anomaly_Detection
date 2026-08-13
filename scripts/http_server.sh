#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)/docs"
HOST="127.0.0.1"
PORT="8000"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--root DIR] [--host HOST] [--port PORT]

静的ファイルを配信する HTTP サーバを起動する。
既定: --root <repo>/docs --host 127.0.0.1 --port 8000
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$ROOT" ]]; then
  echo "配信ディレクトリが見つかりません: $ROOT" >&2
  exit 1
fi
ROOT="$(cd "$ROOT" && pwd)"

echo "Serving ${ROOT} at http://${HOST}:${PORT}/"
echo "Stop with Ctrl+C"
exec python3 -m http.server "$PORT" --bind "$HOST" --directory "$ROOT"
