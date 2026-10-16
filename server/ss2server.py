#!/usr/bin/env python3
"""Surgeon Simulator 2 revival server.

Emulates the Bossa backend the last co-op build (1.5.1.561) talks to:
  TCP  8090  REST API (auth, profile, friends, party, matchmaking, progression, ...)
  UDP  8021  STUN    "SP"+json  -> "SP"+"a.b.c.d:port"
  UDP  8022  TURN    "TP"+json  -> "TP" pong;  "TD"+target(36)+sender(36)+type+payload -> forwarded to target
  UDP  8023  notify  "NP"+json  registers the player's endpoint; server pushes "ND"+playerId(36)+NAME
"""
import argparse
import json
import logging
import os
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

import api
from state import State, same_group

MAX_BODY = 256 * 1024
QUIET = ("/auth/",)   # never log bodies here: Steam tickets and session tokens

log = logging.getLogger("ss2")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SS2Revival/1.0"

    def log_message(self, fmt, *args):
        pass

    timeout = 20   # slow / stuck clients can't hold a thread forever

    def _handle(self, method):
        url = urlsplit(self.path)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else b""
        token = self.headers.get("Security")
        try:
            status, payload = api.dispatch(self.server.state, method, url.path, parse_qs(url.query), body, token, self.headers)
        except Exception:
            log.exception("error in %s %s", method, self.path)
            status, payload = 500, {"error": "internal"}
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload).encode()
            ctype = "application/json"
        elif isinstance(payload, str):
            data = payload.encode()
            ctype = "text/plain"
        else:
            data = payload or b""
            ctype = "application/octet-stream"
        if url.path.startswith(QUIET):
            log.info("%s %s -> %d", method, url.path, status)
        else:
            log.debug("%s %s %s <- %s -> %d %s", method, url.path, ("?" + url.query) if url.query else "",
                      body[:400].decode("utf-8", "replace"), status, data[:400].decode("utf-8", "replace"))
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_PATCH(self):
        self._handle("PATCH")


def udp_loop(state, port, kind):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    state.udp[kind] = sock
    log.info("UDP %s on %d", kind, port)
    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except OSError:
            continue
        if len(data) < 2 or len(data) > 1280:
            continue
        head = data[:2]
        try:
            if kind == "stun" and head == b"SP":
                info = json.loads(data[2:].decode("ascii", "replace") or "{}")
                pid = state.player_for_token(info.get("jwt"))
                if pid:
                    state.set_connection(pid, addr, info.get("clientJson") or "")
                sock.sendto(b"SP" + f"{addr[0]}:{addr[1]}".encode(), addr)
            elif kind == "turn" and head == b"TP":
                info = json.loads(data[2:].decode("ascii", "replace") or "{}")
                pid = state.player_for_token(info.get("jwt"))
                if pid:
                    state.turn_endpoints[pid] = addr
                sock.sendto(b"TP", addr)
            elif kind == "turn" and head == b"TD" and len(data) >= 75:
                target = data[2:38].decode("ascii", "replace")
                sender = data[38:74].decode("ascii", "replace")
                dest = state.turn_endpoints.get(target)
                # only relay for a registered sender, from its own address, to someone in its party/match
                if dest and state.turn_endpoints.get(sender) == addr and same_group(state, sender, target):
                    sock.sendto(data, dest)
                    state.relay_count += 1
            elif kind == "notify" and head == b"NP":
                info = json.loads(data[2:].decode("ascii", "replace") or "{}")
                pid = state.player_for_token(info.get("jwt"))
                if pid:
                    state.notify_endpoints[pid] = addr
        except Exception:
            log.exception("udp %s from %s", kind, addr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--http-port", type=int, default=int(os.environ.get("SS2_HTTP_PORT", 8090)))
    ap.add_argument("--data", default=os.environ.get("SS2_DATA", os.path.join(os.path.dirname(__file__), "data")))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    state = State(args.data)

    def notify(pid, name):
        ep = state.notify_endpoints.get(pid)
        sock = state.udp.get("notify")
        if ep and sock:
            # sent twice: UDP, and the client only refetches on receipt
            pkt = b"ND" + pid.encode() + name.encode()
            sock.sendto(pkt, ep)
            sock.sendto(pkt, ep)
            log.info("notify %s %s", pid[:8], name)
    state.notify = notify

    for port, kind in ((8021, "stun"), (8022, "turn"), (8023, "notify")):
        threading.Thread(target=udp_loop, args=(state, port, kind), daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", args.http_port), Handler)
    srv.state = state
    log.info("HTTP on %d, data in %s", args.http_port, args.data)
    srv.serve_forever()


if __name__ == "__main__":
    main()
