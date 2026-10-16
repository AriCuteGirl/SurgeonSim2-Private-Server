#!/usr/bin/env bash
# Play the patched old build on Linux through Proton (Steam must be installed, but doesn't need to run).
#   linux/play.sh "/path/to/Surgeon Sim 2 Old"
set -euo pipefail
GAME="${1:?usage: play.sh <game folder>}"
STEAM="${STEAM_ROOT:-$HOME/.local/share/Steam}"
PROTON="${PROTON:-}"
if [ -z "$PROTON" ]; then
  for p in "$STEAM/steamapps/common/Proton - Experimental" "$STEAM"/steamapps/common/Proton\ [0-9]*; do
    [ -x "$p/proton" ] && PROTON="$p" && break
  done
fi
[ -x "$PROTON/proton" ] || { echo "Proton not found, set PROTON=/path/to/Proton"; exit 1; }
export STEAM_COMPAT_DATA_PATH="${SS2_PREFIX:-$HOME/.local/share/ss2-revival/prefix}"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM"
export SteamAppId=774791 SteamGameId=774791
mkdir -p "$STEAM_COMPAT_DATA_PATH"
cd "$GAME"
exec "$PROTON/proton" run "./Surgeon Simulator 2.exe" "${@:2}"
