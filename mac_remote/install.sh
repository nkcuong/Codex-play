#!/bin/bash
# Installs Mac Remote as a login item (launchd user agent) so it is always running.
set -euo pipefail
cd "$(dirname "$0")"
SERVER="$(pwd)/server.py"
PLIST="$HOME/Library/LaunchAgents/com.macremote.server.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.mac_remote"
sed -e "s|__SERVER_PATH__|$SERVER|g" -e "s|__HOME__|$HOME|g" com.macremote.server.plist > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
sleep 1
echo "Installed. Server log: $HOME/.mac_remote/server.log"
echo "Access token: $(python3 "$SERVER" --show-token)"
echo "Open http://$(ipconfig getifaddr en0 2>/dev/null || hostname):$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.mac_remote/config.json')))['port'])") on your phone."
