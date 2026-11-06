#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
if [[ ! -e data ]]; then
  runtime_dir="${OPEN_CASTING_RUNTIME_DIR:-$HOME/vault/runtime/open-casting}"
  mkdir -p "$runtime_dir"
  ln -s "$runtime_dir" data
fi
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
.venv/bin/python -m app.db init
exec .venv/bin/python -m app.serve
