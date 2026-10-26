#!/usr/bin/env bash
# One-time setup on macOS / Linux. Run from the claimsaathi folder:  bash setup.sh
set -euo pipefail
cd "$(dirname "$0")/backend"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
cd ../frontend
npm install
npm run build
echo "Setup done. Start the app with:  bash start.sh"
