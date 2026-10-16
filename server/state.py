"""Persistent + live state for the SS2 revival server."""
import json
import os
import secrets
import threading
import time
import uuid


SESSION_SECONDS = 7 * 86400   # the client refreshes every 3.5 h


def same_group(state, a, b):
    """True if two players share a party or a match (only they may relay to each other)."""
    pa = state.party_of.get(a)
    if pa and pa == state.party_of.get(b):
        return True
    ma = state.match_of.get(a)
    return bool(ma and ma == state.match_of.get(b))


class State:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "players.json")
        self.sessions_path = os.path.join(data_dir, "sessions.json")
        self.lock = threading.RLock()
        self.players = {}          # playerId -> {platformUserId, platformName, name, ...}
        self.by_platform = {}      # "Steam:7656..." -> playerId
        self.tokens = {}           # jwt -> {"pid", "exp"}  (persisted, so a server restart doesn't log everyone out)
        self.connections = {}      # playerId -> {"remoteAddress", "remotePort", "clientJson"}
        self.turn_endpoints = {}   # playerId -> (ip, port)
        self.notify_endpoints = {} # playerId -> (ip, port)
        self.last_seen = {}        # playerId -> time
        self.parties = {}          # partyId -> party dict
        self.party_of = {}         # playerId -> partyId
        self.party_invites = []    # {id, partyId, from, to, created}
        self.matches = {}          # matchId -> match dict
        self.match_of = {}         # playerId -> matchId
        self.udp = {}
        self.relay_count = 0
        self.notify = lambda pid, name: None
        self._load()

    # ---- persistence -------------------------------------------------
    def _load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                self.players = json.load(f)
        for pid, p in self.players.items():
            self.by_platform[f"{p['platformName']}:{p['platformUserId']}"] = pid
        if os.path.exists(self.sessions_path):
            with open(self.sessions_path) as f:
                now = time.time()
                self.tokens = {t: v for t, v in json.load(f).items() if v.get("exp", 0) > now}

    def _save_sessions(self):
        tmp = self.sessions_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.tokens, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.sessions_path)

    def save(self):
        with self.lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.players, f, indent=1)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)

    # ---- players -----------------------------------------------------
    def login(self, platform_name, platform_user_id):
        with self.lock:
            key = f"{platform_name}:{platform_user_id}"
            pid = self.by_platform.get(key)
            if not pid:
                pid = str(uuid.uuid4())
                self.by_platform[key] = pid
                self.players[pid] = {
                    "platformName": platform_name,
                    "platformUserId": str(platform_user_id),
                    "name": f"Surgeon{str(platform_user_id)[-4:]}",
                    "created": int(time.time()),
                    "friends": [],
                }
                self.save()
            now = time.time()
            # drop this player's older sessions and anything expired
            self.tokens = {t: v for t, v in self.tokens.items() if v["pid"] != pid and v["exp"] > now}
            token = secrets.token_hex(32)
            self.tokens[token] = {"pid": pid, "exp": now + SESSION_SECONDS}
            self._save_sessions()
            self.last_seen[pid] = now
            return pid, token

    def refresh(self, token):
        with self.lock:
            v = self.tokens.get(token)
            if v:
                v["exp"] = time.time() + SESSION_SECONDS
                self._save_sessions()

    def player_for_token(self, token):
        if not token:
            return None
        v = self.tokens.get(token)
        if not v or v["exp"] < time.time():
            return None
        self.last_seen[v["pid"]] = time.time()
        return v["pid"]

    def set_connection(self, pid, addr, client_json):
        self.connections[pid] = {"remoteAddress": addr[0], "remotePort": addr[1], "clientJson": client_json}

    def online(self, pid, within=90):
        return time.time() - self.last_seen.get(pid, 0) < within

    def player_for_platform(self, platform_name, platform_user_id):
        return self.by_platform.get(f"{platform_name}:{platform_user_id}")
