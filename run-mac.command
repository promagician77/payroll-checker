#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python is not installed. Get it from https://www.python.org/downloads/"; read -r; exit 1
fi
if [ ! -d .venv ]; then
  echo "First run: setting things up, this takes a minute..."
  python3 -m venv .venv && .venv/bin/python -m pip install --quiet -r requirements.txt || { read -r; exit 1; }
fi
.venv/bin/python run.py
