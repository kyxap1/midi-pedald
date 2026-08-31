#!/usr/bin/env bash
# Remove the launchd agent and the daemon bundle. Prompts before deleting the
# config and logs.
set -euo pipefail

LABEL="pro.kyxap.midi-pedald"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
SUPPORT="$HOME/Library/Application Support/midi-pedald"
LOGDIR="$HOME/Library/Logs/midi-pedald"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
rm -f "$PLIST"
echo ">> removed agent and $PLIST"

if [ -d "$SUPPORT/bin" ]; then
    rm -rf "$SUPPORT/bin"
    echo ">> removed $SUPPORT/bin"
fi

read -r -p ">> also delete config and logs ($SUPPORT, $LOGDIR)? [y/N] " ans
if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
    rm -rf "$SUPPORT" "$LOGDIR"
    echo ">> removed config and logs"
else
    echo ">> kept $SUPPORT and $LOGDIR"
fi
