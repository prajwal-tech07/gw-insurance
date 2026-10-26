#!/usr/bin/env bash
# Start ClaimSaathi on macOS / Linux, then open http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")/backend"
[ -d .venv ] || { echo "Run setup.sh first."; exit 1; }
echo "ClaimSaathi is running at http://127.0.0.1:8000  (Ctrl+C to stop)"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
