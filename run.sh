#!/usr/bin/env bash
# One-command setup + launch: creates a venv on first run and installs
# dependencies, then starts the app. Safe to re-run any time -- the
# venv/install step only happens once (delete the .venv/ directory to
# force a clean reinstall).
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python run.py "$@"
