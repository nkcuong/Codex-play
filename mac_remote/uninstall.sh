#!/bin/bash
PLIST="$HOME/Library/LaunchAgents/com.macremote.server.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Mac Remote login item removed. Config kept in ~/.mac_remote (delete it if you like)."
