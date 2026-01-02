#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PORT="${PORT:-8501}"

if [[ ! -x "${ROOT}/.venv/bin/streamlit" ]]; then
  echo "ERROR: .venv not found or streamlit not installed."
  echo "Run:"
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  pip install -r requirements.txt"
  exit 1
fi

exec "${ROOT}/.venv/bin/streamlit" run "${ROOT}/timetable_web_gui.py" \
  --server.address=0.0.0.0 \
  --server.port="${PORT}" \
  --server.headless=true


