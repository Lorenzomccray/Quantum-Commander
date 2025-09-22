#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
HOST="${QC_HOST:-http://127.0.0.1:8000}"
# Load VC token from .env
if [[ -f "$ROOT/.env" ]]; then
  # shellcheck disable=SC2046
  eval $(grep -E '^(VC_TOKEN)=.*' "$ROOT/.env" | sed 's/^/export /') || true
fi
TOKEN="${VC_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  echo "VC_TOKEN not set. Add VC_TOKEN=... to $ROOT/.env" >&2
  exit 1
fi
cmd="${1:-}"; shift || true
case "$cmd" in
  open)
    arg="${1:-}"; shift || true
    if [[ -z "$arg" ]]; then echo "usage: $0 open <path[:line[:col]]>" >&2; exit 2; fi
    path="$arg"; line=1; col=1
    IFS=':' read -r p l c <<<"$arg" || true
    path="$p"
    [[ -n "${l:-}" && "$l" =~ ^[0-9]+$ ]] && line="$l"
    [[ -n "${c:-}" && "$c" =~ ^[0-9]+$ ]] && col="$c"
    curl -fsS -X POST -H "X-VC-Token: $TOKEN" "$HOST/vscode/open?path=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$path")&line=$line&col=$col" | jq -r '.ok // .error // .'
    ;;
  diff)
    left="${1:-}"; right="${2:-}"; shift || true; shift || true
    if [[ -z "$left" || -z "$right" ]]; then echo "usage: $0 diff <left> <right>" >&2; exit 2; fi
    curl -fsS -X POST -H "X-VC-Token: $TOKEN" "$HOST/vscode/diff?left=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$left")&right=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$right")" | jq -r '.ok // .error // .'
    ;;
  workspace)
    curl -fsS -X POST -H "X-VC-Token: $TOKEN" "$HOST/vscode/open-workspace" | jq -r '.ok // .error // .'
    ;;
  *)
    echo "usage: $0 <open|diff|workspace> [...]" >&2
    exit 2
    ;;
esac
