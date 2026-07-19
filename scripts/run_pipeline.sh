#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt >/dev/null

THROUGH="validate"
WITH_PUBLISH=0
FORCE_FETCH=0
FORCE_REBUILD=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Run the NEM data pipeline: fetch -> stage -> mart -> validate -> (optional) publish.

Options:
  --through STAGE       Stop after STAGE (fetch|stage|mart|validate|publish)
  --with-publish        Run publish after validate passes
  --force-fetch         Re-fetch raw artifacts
  --force-rebuild       Rebuild staging and mart artifacts
  -h, --help            Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --through)
      THROUGH="$2"
      shift 2
      ;;
    --with-publish)
      WITH_PUBLISH=1
      shift
      ;;
    --force-fetch)
      FORCE_FETCH=1
      shift
      ;;
    --force-rebuild)
      FORCE_REBUILD=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

ARGS=(--through "$THROUGH")
if [[ "$WITH_PUBLISH" -eq 1 ]]; then
  ARGS+=(--with-publish)
fi
if [[ "$FORCE_FETCH" -eq 1 ]]; then
  ARGS+=(--force-fetch)
fi
if [[ "$FORCE_REBUILD" -eq 1 ]]; then
  ARGS+=(--force-rebuild)
fi

python -m src.publisher.pipeline "${ARGS[@]}"
