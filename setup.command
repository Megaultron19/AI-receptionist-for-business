#!/bin/bash
cd "$(dirname "$0")" || exit 1
fail() { echo "$1"; read -r -p "Press Enter to close"; exit 1; }
command -v python3 >/dev/null || fail "Install Python 3.12 or newer from python.org first."
[ -d .venv ] || python3 -m venv .venv || fail "Could not create the Python environment."
.venv/bin/pip install -r backend/requirements.txt || fail "Could not install the Python packages."
if [ ! -d frontend/out ]; then
  command -v npm >/dev/null || fail "Install Node.js LTS from nodejs.org to build the dashboard."
  (cd frontend && npm ci && npm run build) || fail "Could not build the dashboard."
fi
.venv/bin/python setup.py || fail "Setup did not finish."
read -r -p "Press Enter to close"
