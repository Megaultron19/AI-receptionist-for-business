#!/bin/bash
cd "$(dirname "$0")/backend" || exit 1
read -r -p "Username to reset (usually owner): " name
../.venv/bin/python -m app.cli reset-password "$name"
read -r -p "Press Enter to close"
