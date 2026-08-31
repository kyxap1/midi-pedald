#!/usr/bin/env bash
# Unload and remove the launchd agent. Leaves config and logs alone.
set -euo pipefail

LABEL="pro.kyxap.pedald"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo ">> removed $PLIST"
echo ">> config / logs kept; delete ~/Library/Application Support/pedald/ to remove them"
