#!/usr/bin/env python3
"""Command-line admin tool for the Surgeon Simulator 2 server (used by Server Manager).

Every command prints one JSON object. Errors: {"ok": false, "error": "..."}, exit code 1.
Files are written atomically (temp file + rename).

The running server keeps players in memory and saves them on its own, so it would
overwrite a change made by "set" or "reset". Stop the server first (Server Manager
does this for you), then start it again.

usage: manage.py [--root DIR] <command> [args]

  info                         game, version, number of players
  players                      all players (no session tokens, no Steam ids)
  player <id>                  one player record
  set <id> xp <value>          change a player's XP (keeps data/players.json.bak)
  reset <id>                   XP, daily challenges and tutorial flags back to new;
                               name and friends kept (old file kept as players.json.old)
  settings                     this game has no settings file: {}
  backup [file]                save data/*.json into a .tar.gz
  backups                      list the backups in backups/
  restore <file>               replace data/ with a backup; old data kept aside
  logs [lines]                 the server logs to the system journal only: []

--root is the folder with ss2server.py (default: the folder of this file). Server Manager
passes it because it runs this script through "python3 -" over SSH.
"""
import json
import os
import shutil
import sys
import tarfile
import time

VERSION = "1.0.0"
GAME = "surgeon-sim-2"
SESSION_SECONDS = 7 * 86400  # same as state.py

# Fields an admin may change with "set" (also in manager/game.json "currencies").
CURRENCIES = {"xp": (0, 100_000_000)}

# Never shown: Steam ids, session tokens, friend lists' ids, profile blobs.
HIDDEN = {"platformUserId", "friends", "profileJson", "daily"}


class Fail(Exception):
    pass


def out(obj, code=0):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.exit(code)


def write_json(path, obj, indent=1):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=indent)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        if default is not None:
            return default
        raise Fail("file not found: %s" % os.path.basename(path))
    except ValueError:
        raise Fail("broken JSON in %s" % os.path.basename(path))


def is_test(p):
    # players made by tests/smoke_test.py; the server drops them on start
    return bool(p.get("test")) or str(p.get("platformUserId", "")).startswith("765611900000001")


class Server:
    def __init__(self, root):
        self.root = os.path.abspath(os.path.expanduser(root))
        self.data = os.path.join(self.root, "data")
        self.players_file = os.path.join(self.data, "players.json")
        self.sessions_file = os.path.join(self.data, "sessions.json")
        self.backup_dir = os.path.join(self.root, "backups")

    def all_players(self):
        players = read_json(self.players_file, {})
        return {pid: p for pid, p in players.items() if not is_test(p)}

    def last_logins(self):
        """Last login/refresh per player, from session expiry times (exp = login + 7 days)."""
        last = {}
        for v in read_json(self.sessions_file, {}).values():
            pid, exp = v.get("pid"), v.get("exp", 0)
            if pid and exp:
                last[pid] = max(last.get(pid, 0), int(exp - SESSION_SECONDS))
        return last

    @staticmethod
    def summary(pid, p, last):
        return {
            "id": pid,
            "name": p.get("name") or "Player %s" % pid[:4],
            "xp": p.get("xp", 0),
            "friends": len(p.get("friends", [])),
            "created": p.get("created"),
            "lastLogin": last.get(pid) or p.get("created") or 0,
        }

    def find(self, players, pid):
        if pid not in players:
            raise Fail("no player %s" % pid)
        return players[pid]

    def players(self):
        last = self.last_logins()
        result = [self.summary(pid, p, last) for pid, p in self.all_players().items()]
        result.sort(key=lambda p: p["lastLogin"] or 0, reverse=True)
        return result

    def player(self, pid):
        p = self.find(self.all_players(), pid)
        rec = {k: v for k, v in p.items() if k not in HIDDEN}
        rec["platformName"] = p.get("platformName")
        rec["dailyChallenges"] = len((p.get("daily") or {}).get("slots", []))
        rec.update(self.summary(pid, p, self.last_logins()))
        return rec

    def set(self, pid, field, value):
        if field not in CURRENCIES:
            raise Fail("unknown field %r, allowed: %s" % (field, ", ".join(CURRENCIES)))
        try:
            value = int(value)
        except ValueError:
            raise Fail("value must be a whole number")
        lo, hi = CURRENCIES[field]
        if not lo <= value <= hi:
            raise Fail("%s must be between %d and %d" % (field, lo, hi))
        players = read_json(self.players_file)
        p = self.find(players, pid)
        old = p.get(field, 0)
        shutil.copy2(self.players_file, self.players_file + ".bak")
        p[field] = value
        write_json(self.players_file, players)
        return {"old": old, "new": value, "backup": "players.json.bak"}

    def reset(self, pid):
        players = read_json(self.players_file)
        p = self.find(players, pid)
        shutil.copy2(self.players_file, self.players_file + ".old")
        p["xp"] = 0
        p["daily"] = {}
        p["profileJson"] = "{}"
        write_json(self.players_file, players)
        return {"kept": "players.json.old", "keptFields": ["name", "friends", "platformName"]}

    # ---- backups -------------------------------------------------------------------
    def backup(self, dest=None):
        if not os.path.isfile(self.players_file):
            raise Fail("no server data in %s" % self.data)
        if dest:
            dest = os.path.abspath(os.path.expanduser(dest))
        else:
            dest = os.path.join(self.backup_dir, "ss2-data-%s.tar.gz" % time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".part"
        with tarfile.open(tmp, "w:gz") as tar:
            tar.add(self.data, arcname="data", recursive=False)
            for name in sorted(os.listdir(self.data)):
                if name.endswith(".json"):  # players + sessions; not .bak/.old/.tmp
                    tar.add(os.path.join(self.data, name), arcname="data/" + name)
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest)
        info = backup_info(dest)
        info.update(file=dest, size=os.path.getsize(dest))
        return info

    def backups(self):
        if not os.path.isdir(self.backup_dir):
            return []
        items = []
        for n in os.listdir(self.backup_dir):
            if n.endswith(".tar.gz"):
                p = os.path.join(self.backup_dir, n)
                st = os.stat(p)
                items.append({"file": p, "name": n, "size": st.st_size, "time": int(st.st_mtime)})
        items.sort(key=lambda b: b["time"], reverse=True)
        return items

    def restore(self, src):
        src = os.path.abspath(os.path.expanduser(src))
        info = backup_info(src)
        kept = None
        with tarfile.open(src) as tar:
            members = safe_members(tar)
            if os.path.exists(self.data):
                kept = self.data + ".before-restore-" + time.strftime("%Y%m%d-%H%M%S")
                shutil.move(self.data, kept)
            tar.extractall(self.root, members=members)
        os.chmod(self.data, 0o700)
        return {"kept": kept, "players": info["players"]}

    def info(self):
        return {"game": GAME, "version": VERSION, "players": len(self.all_players()),
                "data_dir": self.data, "python": "%d.%d.%d" % sys.version_info[:3]}


def safe_members(tar):
    members = tar.getmembers()
    for m in members:
        if (m.name != "data" and not m.name.startswith("data/")) or ".." in m.name.split("/") \
                or m.name.startswith("/") or not (m.isfile() or m.isdir()):
            raise Fail("unexpected entry in backup: %s" % m.name)
    return members


def backup_info(path):
    if not os.path.isfile(path):
        raise Fail("backup not found: %s" % path)
    try:
        with tarfile.open(path) as tar:
            if "data/players.json" not in tar.getnames():
                raise Fail("not a Surgeon Simulator 2 backup (no data/players.json)")
            safe_members(tar)
            players = json.load(tar.extractfile("data/players.json"))
    except tarfile.TarError as e:
        raise Fail("cannot read backup: %s" % e)
    except ValueError:
        raise Fail("broken players.json in backup")
    return {"players": len([p for p in players.values() if not is_test(p)])}


def main(argv):
    me = globals().get("__file__") or ""
    root = os.path.dirname(os.path.abspath(me)) if os.path.isfile(me) else None
    if len(argv) >= 2 and argv[0] == "--root":
        root, argv = argv[1], argv[2:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        out({"ok": True, "help": __doc__})
    if not root or not os.path.isdir(os.path.expanduser(root)):
        raise Fail("server folder not found (use --root DIR): %s" % (root or "not given"))
    srv = Server(root)
    cmd, args = argv[0], argv[1:]

    def need(n, usage):
        if len(args) < n:
            raise Fail("usage: manage.py " + usage)

    if cmd == "info":
        return srv.info()
    if cmd == "players":
        return {"players": srv.players()}
    if cmd == "player":
        need(1, "player <id>")
        return {"player": srv.player(args[0])}
    if cmd == "set":
        need(3, "set <id> xp <value>")
        return srv.set(*args[:3])
    if cmd == "reset":
        need(1, "reset <id>")
        return srv.reset(args[0])
    if cmd == "settings":
        if args:
            raise Fail("this game has no settings file")
        return {"settings": {}}
    if cmd == "codes":
        raise Fail("this game has no promo codes")
    if cmd == "backup":
        return srv.backup(args[0] if args else None)
    if cmd == "backups":
        return {"backups": srv.backups()}
    if cmd == "restore":
        need(1, "restore <file>")
        return srv.restore(args[0])
    if cmd == "logs":
        return {"lines": []}
    raise Fail("unknown command %r (try: manage.py help)" % cmd)


if __name__ == "__main__":
    try:
        result = main(sys.argv[1:])
    except Fail as e:
        out({"ok": False, "error": str(e)}, 1)
    except Exception as e:  # never print a traceback with paths/secrets to the GUI
        out({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 1)
    out(dict(ok=True, **result))
