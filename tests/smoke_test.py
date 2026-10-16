#!/usr/bin/env python3
"""Smoke test against a running server:  python3 tests/smoke_test.py [host] [http_port]
Two fake players log in, form a party, relay a packet; an outsider must be refused.
Test players are hidden from friend lists and removed when the server restarts."""
import json
import socket
import sys
import urllib.request
import urllib.error

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8090
BASE = f"http://{HOST}:{PORT}"


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None)
    if token:
        req.add_header("Security", token)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = r.read()
            return r.status, json.loads(data) if data[:1] in b"[{" else data.decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def login(steamid):
    s, j = call("POST", "/auth/authenticate", {"platformName": "smoketest", "platformUserId": steamid, "platformSecret": "x"})
    assert s == 200, (s, j)
    return j["playerId"], j["jwt"]


def udp(port, payload, src):
    src.sendto(payload, (HOST, port))
    try:
        return src.recv(2048)
    except socket.timeout:
        return None


ok = lambda msg: print("  ok  " + msg)
assert call("GET", "/auth/healthcheck")[0] == 200; ok("healthcheck")
assert call("GET", "/friend/players/00000000-0000-0000-0000-000000000000/friends")[0] == 401; ok("no token -> 401")

a, ta = login("76561190000000101")
b, tb = login("76561190000000102")
c, tc = login("76561190000000103")
assert call("POST", f"/profile/players/{a}", {"userName": "evil"}, tb)[0] == 403; ok("can't edit someone else's profile")

s, party = call("POST", f"/party/players/{a}/parties", {"maxNumPlayers": 4}, ta)
assert s == 200
s, inv = call("POST", f"/party/players/{a}/invitations", {"targetPlayerId": b}, ta)
assert s == 200
assert call("POST", f"/party/players/{c}/invitations/{inv['id']}/accept", None, tc)[0] == 404; ok("outsider can't steal an invite")
s, joined = call("POST", f"/party/players/{b}/invitations/{inv['id']}/accept", None, tb)
assert s == 200 and len(joined["members"]) == 2; ok("invite accepted, party of 2")
assert call("POST", f"/party/parties/{party['id']}/lock", None, tc)[0] == 403; ok("outsider can't lock the party")

# UDP: register turn endpoints, relay a->b works, c->b refused
sa, sb, sc = (socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(3))
for s_, t in ((sa, ta), (sb, tb), (sc, tc)):
    s_.settimeout(2)
    assert udp(8022, b"TP" + json.dumps({"playerId": "", "jwt": t}).encode(), s_) == b"TP"
r = udp(8021, b"SP" + json.dumps({"jwt": ta}).encode(), sa)
assert r and r.startswith(b"SP"); ok("STUN -> " + r[2:].decode())
pkt = b"TD" + b.encode() + a.encode() + b"\x01" + b"hello"
sa.sendto(pkt, (HOST, 8022))
assert sb.recv(2048) == pkt; ok("relay a -> b")
sc.sendto(b"TD" + b.encode() + c.encode() + b"\x01" + b"spam", (HOST, 8022))
try:
    sb.recv(2048)
    raise AssertionError("outsider packet was relayed")
except socket.timeout:
    ok("relay refuses outsiders")

s, d = call("GET", f"/challenges/challenges/players/{a}/currentDailyChallenges", None, ta)
assert s == 200 and len(d["challenges"]) == 3; ok("3 daily challenges")
s, _ = call("POST", f"/party/parties/{party['id']}/removeMember", {"targetPlayerId": b, "autoMigrate": True}, tb)
assert s == 200; ok("member can leave")
print("ALL OK")
