#!/usr/bin/env bash
# Deploy the SS2 revival server to an Ubuntu VM (e.g. Oracle Cloud free tier) as a systemd service:
#   bash deploy/deploy_oracle.sh
# Re-running updates the code; player data in ~/ss2-server/data is kept.
# Needs open ports: TCP 8090 (REST) and UDP 8021-8023 (STUN / relay / notifications).
# Settings: deploy/deploy.env (see deploy.env.example) or env SS2_HOST (user@ip), SS2_KEY (ssh key).
set -euo pipefail

ENV_FILE="$(dirname "$0")/deploy.env"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
HOST="${SS2_HOST:?set SS2_HOST, e.g. ubuntu@1.2.3.4 (see deploy/deploy.env.example)}"
KEY="${SS2_KEY:-$HOME/.ssh/id_ed25519}"
IP="${HOST#*@}"
SSH=(/usr/bin/ssh -i "$KEY" -o StrictHostKeyChecking=accept-new)

cd "$(dirname "$0")/.."

echo "== copying server code"
"${SSH[@]}" "$HOST" 'mkdir -p ~/ss2-server/data ~/ss2-server/news && chmod 700 ~/ss2-server/data'
/usr/bin/scp -i "$KEY" server/ss2server.py server/api.py server/state.py server/challenges.py "$HOST":ss2-server/
/usr/bin/scp -i "$KEY" server/news/*.png "$HOST":ss2-server/news/

echo "== installing service + opening ports"
"${SSH[@]}" "$HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
sudo tee /etc/systemd/system/ss2.service >/dev/null <<UNIT
[Unit]
Description=Surgeon Simulator 2 revival server
After=network-online.target

[Service]
User=$USER
WorkingDirectory=$HOME/ss2-server
Environment=SS2_DATA=$HOME/ss2-server/data
ExecStart=/usr/bin/python3 -u $HOME/ss2-server/ss2server.py
Restart=always
RestartSec=3
# sandbox: the server can only write its own data folder and only use the network
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$HOME/ss2-server/data
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictNamespaces=yes
LockPersonality=yes
MemoryMax=300M
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT
# Oracle's Ubuntu images REJECT everything not explicitly allowed in iptables.
open() {
  if ! sudo iptables -C INPUT -p "$1" --dport "$2" -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 5 -p "$1" --dport "$2" -j ACCEPT
  fi
}
open tcp 8090; open udp 8021; open udp 8022; open udp 8023
sudo netfilter-persistent save >/dev/null 2>&1 || sudo sh -c 'iptables-save > /etc/iptables/rules.v4'
sudo systemctl daemon-reload
sudo systemctl enable --now ss2.service
sudo systemctl restart ss2.service
sleep 2
systemctl --no-pager --lines=3 status ss2.service | head -5
curl -s -w '  <- local check\n' http://127.0.0.1:8090/auth/healthcheck
REMOTE

echo
echo "== checking from here"
curl -s -m 8 -w '  <- public HTTP check\n' "http://$IP:8090/auth/healthcheck" \
  || echo "public check FAILED: add Ingress rules to the VM subnet's Security List in the Oracle console: TCP 8090 and UDP 8021-8023, source 0.0.0.0/0"
python3 - "$IP" <<'PY'
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(4)
s.sendto(b'SP{}', (sys.argv[1], 8021))
try:
    print("public UDP check (STUN 8021):", s.recv(100)[2:].decode(), "<- that's your public address")
except OSError:
    print("public UDP check FAILED: open UDP 8021-8023 in the Oracle Security List")
PY
