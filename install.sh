#!/usr/bin/env bash
# Build the venv, render the launchd plist with real paths, load the agent.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.rc5.midiobs"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$HOME/Library/Logs/midiobs"
VENV="$APP_DIR/.venv"
CONFIG="${MIDIOBS_CONFIG:-$APP_DIR/config.yaml}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo ">> project : $APP_DIR"
echo ">> venv    : $VENV"
echo ">> config  : $CONFIG"

if [ ! -d "$VENV" ]; then
    echo ">> creating venv"
    "$PYTHON_BIN" -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

if [ ! -f "$CONFIG" ]; then
    echo ">> writing starter config from config.example.yaml (edit it, then reload)"
    cp "$APP_DIR/config.example.yaml" "$CONFIG"
fi

mkdir -p "$LOG_DIR" "$(dirname "$PLIST")"

sed -e "s|__PYTHON__|$VENV/bin/python3|g" \
    -e "s|__APP_DIR__|$APP_DIR|g" \
    -e "s|__CONFIG__|$CONFIG|g" \
    -e "s|__LOG_DIR__|$LOG_DIR|g" \
    "$APP_DIR/launchd/${LABEL}.plist.template" >"$PLIST"
echo ">> wrote $PLIST"

# 'unload' fails on first install when nothing is loaded yet; that is fine.
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo ">> loaded. status:"
launchctl list | grep "$LABEL" || echo "   (not listed yet - check $LOG_DIR)"
