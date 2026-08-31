#!/usr/bin/env bash
# Remove everything the .pkg installed except the config at ~/.config/midi-pedald/.
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

rm -rf "${SUPPORT:?}" "${LOGDIR:?}"
echo ">> removed $SUPPORT and $LOGDIR"

# currentUserHome receipts live under $HOME, not /var/db/receipts.
if pkgutil --volume "$HOME" --pkg-info "$LABEL" >/dev/null 2>&1; then
    pkgutil --volume "$HOME" --forget "$LABEL"
fi

echo ">> kept config at $CONFDIR"
