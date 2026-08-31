#!/usr/bin/env bash
# Remove the launchd agent and the daemon bundle. Prompts before deleting the
# config and logs.
set -euo pipefail

LABEL="pro.kyxap.midi-pedald"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
SUPPORT="${HOME:?}/Library/Application Support/midi-pedald"
CONFDIR="${HOME:?}/.config/midi-pedald"
LOGDIR="${HOME:?}/Library/Logs/midi-pedald"

if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/${LABEL}"
fi
rm -f "$PLIST"
echo ">> removed agent and $PLIST"

if [ -d "$SUPPORT" ]; then
    rm -rf "${SUPPORT:?}"
    echo ">> removed $SUPPORT"
fi

read -r -p ">> also delete config and logs ($CONFDIR, $LOGDIR)? [y/N] " ans
if [ "$ans" = "y" ] || [ "$ans" = "Y" ]; then
    rm -rf "${CONFDIR:?}" "${LOGDIR:?}"
    echo ">> removed config and logs"
else
    echo ">> kept $CONFDIR and $LOGDIR"
fi
