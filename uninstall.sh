#!/usr/bin/env bash
# Unload and remove the launchd agent. Leaves venv, config and logs alone.
set -euo pipefail

LABEL="com.rc5.midiobs"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

# 'unload' fails if it was never loaded; that is fine.
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo ">> removed $PLIST"
echo ">> venv / config / logs kept; delete the project directory to remove them"
