#!/usr/bin/env bash
set -euo pipefail

# Simple bootstrap: create venv, install deps, run web UI
PY=${PYTHON:-python3}
VENV=.venv
if [ ! -d "$VENV" ]; then
  echo "[bootstrap] creating venv"
  $PY -m venv "$VENV"
fi
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null
if ! pip install -r requirements.txt; then
  echo "[bootstrap] optional extras failed; installing core deps only"
  pip install Flask openai python-dotenv || true
fi

PORT=${PORT:-5000}
export PORT
export FLASK_DEBUG=1
echo "[bootstrap] starting Web UI on port $PORT"
exec python -m web_ui.app
