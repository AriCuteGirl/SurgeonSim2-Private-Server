#!/usr/bin/env bash
# Build the release downloads (no game files inside):
#   dist/SS2Revival-Windows.zip   SS2Revival-Installer.exe + RevivalMod.dll + pupberg/steam_api64.dll
#   dist/SS2Revival-Linux.tar.gz  same for Linux + play.sh
# The public downloads contain no server address (the installer asks for it).
# With SS2_SERVER=<ip> (or deploy/deploy.env) it also builds dist/private/*-<ip> with server.txt
# baked in, for sending to your friends directly. Don't upload those.
# Needs: .NET 8 SDK, gh (PupBerg download), and your own copy of the game for compiling RevivalMod:
#   GAME_MANAGED="/path/Surgeon Simulator 2_Data/Managed" tools/package.sh
set -euo pipefail
cd "$(dirname "$0")/.."
: "${GAME_MANAGED:?set GAME_MANAGED to <game>/Surgeon Simulator 2_Data/Managed}"
PUPBERG_TAG="${PUPBERG_TAG:-release-pupberg-0.1.6}"
rm -rf dist build/pkg && mkdir -p dist build/pkg

dotnet build tools/RevivalMod -c Release -p:GameManaged="$GAME_MANAGED" -o build/pkg/revivalmod
gh release download "$PUPBERG_TAG" -R AriCuteGirl/PupBerg -p PupBerg-Windows.zip -D build/pkg --clobber
unzip -q -o build/pkg/PupBerg-Windows.zip -d build/pkg/pupberg

for rid in win-x64 linux-x64; do
  out=build/pkg/$rid
  dotnet publish tools/Installer -c Release -r $rid --self-contained true -p:PublishSingleFile=true \
    -p:EnableCompressionInSingleFile=true -p:DebugType=none -o $out
  cp build/pkg/revivalmod/RevivalMod.dll $out/
  mkdir -p $out/pupberg && cp build/pkg/pupberg/PupBerg-Windows/steam_api64.dll $out/pupberg/
  cp README.md $out/README.md
done
cp linux/play.sh build/pkg/linux-x64/
(cd build/pkg/win-x64 && zip -qr ../../../dist/SS2Revival-Windows.zip .)
tar -C build/pkg/linux-x64 -czf dist/SS2Revival-Linux.tar.gz .

[ -f deploy/deploy.env ] && . deploy/deploy.env
SS2_SERVER="${SS2_SERVER:-${SS2_HOST#*@}}"
if [ -n "$SS2_SERVER" ]; then
  mkdir -p dist/private
  for rid in win-x64 linux-x64; do
    printf 'host=%s\nport=8090\npupberg_lobby=%s:47620\nroom=%s\n' "$SS2_SERVER" "$SS2_SERVER" "${SS2_ROOM:-SS2-REVIVAL}" > build/pkg/$rid/server.txt
  done
  (cd build/pkg/win-x64 && zip -qr "../../../dist/private/SS2Revival-Windows-$SS2_SERVER.zip" .)
  tar -C build/pkg/linux-x64 -czf "dist/private/SS2Revival-Linux-$SS2_SERVER.tar.gz" .
  rm build/pkg/*/server.txt
fi
ls -la dist dist/private 2>/dev/null
