#!/usr/bin/env bash
# Copy the server's player data (players.json, sessions.json) from the VM to backups/<date>/.
#   bash deploy/backup.sh
set -euo pipefail
ENV_FILE="$(dirname "$0")/deploy.env"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
HOST="${SS2_HOST:?set SS2_HOST (see deploy/deploy.env.example)}"
KEY="${SS2_KEY:-$HOME/.ssh/id_ed25519}"
cd "$(dirname "$0")/.."
DEST="backups/$(date +%Y-%m-%d_%H%M)"
mkdir -p "$DEST" && chmod 700 backups "$DEST"
/usr/bin/scp -i "$KEY" "$HOST":ss2-server/data/'*.json' "$DEST"/
ls -la "$DEST"
