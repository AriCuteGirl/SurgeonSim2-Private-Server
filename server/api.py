"""REST routes of the SS2 revival server.

Response shapes come from the client's own parsers (Assembly-CSharp, Services/*Api.cs).
"""
import json
import logging
import os
import re
import time
import uuid

import challenges

log = logging.getLogger("ss2.api")

ROUTES = []
UUID = r"([0-9a-fA-F-]{32,36})"
NEWS_DIR = os.path.join(os.path.dirname(__file__), "news")


def route(method, pattern, public=False):
    """public=True: no login needed (health/version/news/login). Everything else needs a valid session."""
    rx = re.compile("^" + pattern + "$")

    def deco(fn):
        ROUTES.append((method, rx, fn, public))
        return fn
    return deco


OWN_PATH = re.compile(r"/players/([0-9a-fA-F-]{32,36})(/|$)")


def dispatch(state, method, path, query, body, token, headers):
    for m, rx, fn, public in ROUTES:
        if m == method:
            mt = rx.match(path)
            if mt:
                req = Request(state, method, path, query, body, token, headers)
                if not public:
                    if not req.player:
                        return 401, {"error": "UNAUTHORIZED"}
                    # writes to /players/<id>/... are only allowed for your own id
                    own = OWN_PATH.search(path)
                    if method != "GET" and own and own.group(1) != req.player:
                        return 403, {"error": "UNAUTHORIZED"}
                with state.lock:
                    return fn(req, *mt.groups())
    log.warning("UNHANDLED %s %s", method, path)
    return 404, {"error": "NOT_FOUND"}


class Request:
    def __init__(self, state, method, path, query, body, token, headers):
        self.state, self.method, self.path, self.query = state, method, path, query
        self.body, self.token, self.headers = body, token, headers
        self.player = state.player_for_token(token)

    def json(self):
        try:
            return json.loads(self.body or b"{}")
        except ValueError:
            return {}


def now_ms():
    return int(time.time() * 1000)


def member(state, pid):
    c = state.connections.get(pid) or {"remoteAddress": "0.0.0.0", "remotePort": 0, "clientJson": '{"localEndPoints":""}'}
    return {"id": pid, "connectionDetails": dict(c)}


# ---- health / status / news ------------------------------------------
@route("GET", r"/auth/healthcheck", public=True)
def healthcheck(req):
    return 200, "OK"


@route("GET", r"/version", public=True)
def version(req):
    return 200, '"1.0.0"'


@route("GET", r"/status", public=True)
def status(req):
    return 200, '"ONLINE"'


@route("GET", r"/scheduledTimes", public=True)
def scheduled(req):
    return 200, {"maintenanceMode": []}


@route("GET", r"/news/NewsFeed\.json", public=True)
def news(req):
    return 200, {"NewsTiles": [
        {"ImageUrl": "revival.png", "ClickUrl": "https://github.com/AriCuteGirl",
         "Title": "PRIVATE SERVER BY ARI",
         "SubTitle": "Surgeon Simulator 2 co-op is back. Grab a scalpel and try not to lose the patient (or your arm)."},
        {"ImageUrl": "coop.png", "ClickUrl": "https://github.com/AriCuteGirl",
         "Title": "Co-op is back",
         "SubTitle": "Everyone on this server is your friend. Open the party menu and invite them in."},
        {"ImageUrl": "pupberg.png", "ClickUrl": "https://github.com/AriCuteGirl/PupBerg",
         "Title": "Powered by PupBerg",
         "SubTitle": "No Steam servers needed. Press Shift+Tab for the PupBerg overlay."},
    ]}


@route("GET", r"/news/images/([A-Za-z0-9._-]+)", public=True)
def news_image(req, name):
    p = os.path.join(NEWS_DIR, name)
    if os.path.isfile(p):
        with open(p, "rb") as f:
            return 200, f.read()
    return 404, b""


# ---- auth ------------------------------------------------------------
@route("POST", r"/auth/authenticate", public=True)
def authenticate(req):
    j = req.json()
    uid = str(j.get("platformUserId", ""))
    if not uid.isdigit() or len(uid) > 20:
        return 400, {"error": "BAD_PLATFORM_USER"}
    pid, token = req.state.login(str(j.get("platformName", "steam"))[:16], uid)
    log.info("login %s %s -> %s", j.get("platformName"), j.get("platformUserId"), pid)
    return 200, {"playerId": pid, "jwt": token}


@route("POST", r"/auth/refreshJWT", public=True)
def refresh(req):
    if not req.player:
        return 401, {"error": "UNAUTHORIZED"}
    req.state.refresh(req.token)
    return 200, {"playerId": req.player, "jwt": req.token}


@route("POST", r"/auth/addfriend")
def addfriend(req):
    # Steam (PupBerg) friend list sync: everyone on this server is already friends with everyone.
    return 200, {}


# ---- profile ---------------------------------------------------------
def profile_json(state, pid):
    p = state.players[pid]
    return {"playerId": pid, "userName": p.get("name", "Surgeon"), "profileJson": p.get("profileJson", ""),
            "platformName": p["platformName"], "platformUserId": p["platformUserId"]}


@route("GET", r"/profile/players/" + UUID)
def get_profile(req, pid):
    if pid not in req.state.players:
        return 404, {"error": "PROFILE_NOT_FOUND"}
    return 200, profile_json(req.state, pid)


@route("POST", r"/profile/players/" + UUID)
def set_profile(req, pid):
    if req.player != pid:
        return 403, {"error": "UNAUTHORIZED"}
    j = req.json()
    p = req.state.players[pid]
    if j.get("userName"):
        p["name"] = "".join(c for c in str(j["userName"]) if c.isprintable())[:32] or p.get("name", "Surgeon")
    if isinstance(j.get("profileJson"), str) and len(j["profileJson"]) <= 16384:
        p["profileJson"] = j["profileJson"]
    req.state.save()
    return 200, profile_json(req.state, pid)


@route("GET", r"/profile/search")
def search_profile(req):
    name = (req.query.get("userName") or [""])[0].lower()
    return 200, [profile_json(req.state, pid) for pid, p in req.state.players.items()
                 if name and name in p.get("name", "").lower()]


# ---- friends: everyone on the server is a friend ---------------------
@route("GET", r"/friend/players/" + UUID + r"/friends")
def friends(req, pid):
    st = req.state
    return 200, [{"playerId": o, "online": st.online(o)} for o in st.players if o != pid]


@route("GET", r"/friend/players/" + UUID + r"/invitations/(sent|received)")
def friend_invites(req, pid, kind):
    return 200, []


@route("POST", r"/friend/players/" + UUID + r"/(invitations|unfriend)")
def friend_invite(req, pid, kind):
    return 200, {}


@route("POST", r"/friend/players/" + UUID + r"/invitations/" + UUID + r"/(cancel|accept|reject)")
def friend_invite_act(req, pid, iid, act):
    return 200, {}


# ---- party -----------------------------------------------------------
def party_json(state, party):
    return {"id": party["id"], "leaderPlayerId": party["leader"], "maxNumPlayers": party["max"],
            "locked": party["locked"], "members": [member(state, m) for m in party["members"]]}


def notify_party(state, party, what="PARTY_PARTY", skip=None):
    for m in party["members"]:
        if m != skip:
            state.notify(m, what)


def leave_party(state, pid):
    old = state.party_of.pop(pid, None)
    party = state.parties.get(old)
    if not party:
        return
    if pid in party["members"]:
        party["members"].remove(pid)
    if not party["members"]:
        del state.parties[old]
        return
    if party["leader"] == pid:
        party["leader"] = party["members"][0]
    notify_party(state, party)


def join_party(state, pid, party):
    if state.party_of.get(pid) == party["id"]:
        return
    leave_party(state, pid)
    party["members"].append(pid)
    state.party_of[pid] = party["id"]
    notify_party(state, party, skip=pid)


def new_party(state, leader, max_players=4, party_id=None):
    leave_party(state, leader)
    party = {"id": party_id or str(uuid.uuid4()), "leader": leader, "max": max_players, "locked": False, "members": [leader]}
    state.parties[party["id"]] = party
    state.party_of[leader] = party["id"]
    return party


def my_party(req, pid):
    party = req.state.parties.get(req.state.party_of.get(pid))
    return party


@route("GET", r"/party/players/" + UUID + r"/parties")
def get_party(req, pid):
    party = my_party(req, pid)
    if not party:
        return 404, {"error": "PLAYER_NOT_IN_PARTY"}
    return 200, party_json(req.state, party)


@route("POST", r"/party/players/" + UUID + r"/parties")
def create_party(req, pid):
    party = new_party(req.state, pid, int(req.json().get("maxNumPlayers") or 4))
    return 200, party_json(req.state, party)


@route("POST", r"/party/parties/" + UUID)
def create_or_join(req, party_id):
    st = req.state
    j = req.json()
    pid = req.player
    party = st.parties.get(party_id)
    if not party:
        party = new_party(st, pid, int(j.get("maxNumPlayers") or 4), party_id)
    else:
        if pid not in party["members"]:
            if party["locked"]:
                return 409, {"error": "PARTY_IS_LOCKED"}
            if len(party["members"]) >= party["max"]:
                return 409, {"error": "PARTY_IS_FULL"}
            join_party(st, pid, party)
    return 200, party_json(st, party)


@route("POST", r"/party/parties/" + UUID + r"/(updateConfig|changeLeader|lock|unlock|removeMember)")
def party_action(req, party_id, act):
    st = req.state
    party = st.parties.get(party_id)
    if not party:
        return 404, {"error": "PARTY_DOES_NOT_EXIST"}
    if req.player not in party["members"]:
        return 403, {"error": "PLAYER_NOT_IN_PARTY"}
    j = req.json()
    if act in ("updateConfig", "changeLeader", "lock", "unlock") and req.player != party["leader"]:
        return 403, {"error": "NOT_PARTY_LEADER"}
    if act == "removeMember" and j.get("targetPlayerId") not in (req.player, party["leader"]) and req.player != party["leader"]:
        return 403, {"error": "NOT_PARTY_LEADER"}
    if act == "updateConfig":
        party["max"] = int(j.get("maxNumPlayers") or party["max"])
    elif act == "changeLeader" and j.get("targetPlayerId") in party["members"]:
        party["leader"] = j["targetPlayerId"]
    elif act == "lock":
        party["locked"] = True
    elif act == "unlock":
        party["locked"] = False
    elif act == "removeMember":
        target = j.get("targetPlayerId")
        if target in party["members"]:
            leave_party(st, target)
            st.notify(target, "PARTY_PARTY")
            return 200, party_json(st, party) if party_id in st.parties else {}
    notify_party(st, party)
    return 200, party_json(st, party)


def invite_json(inv):
    return {"id": inv["id"], "inviterPlayerId": inv["from"], "inviteePlayerId": inv["to"], "message": "",
            "invitationStatus": "PENDING", "lastUpdatedDate": inv["created"]}


@route("GET", r"/party/players/" + UUID + r"/invitations/(sent|received)")
def party_invites(req, pid, kind):
    key = "from" if kind == "sent" else "to"
    return 200, [invite_json(i) for i in req.state.party_invites if i[key] == pid]


@route("POST", r"/party/players/" + UUID + r"/invitations")
def party_invite(req, pid):
    st = req.state
    target = req.json().get("targetPlayerId")
    if target not in st.players:
        return 404, {"error": "PLAYER_DOES_NOT_EXIST"}
    party = my_party(req, pid) or new_party(st, pid)
    st.party_invites = [i for i in st.party_invites if not (i["from"] == pid and i["to"] == target)]
    inv = {"id": str(uuid.uuid4()), "partyId": party["id"], "from": pid, "to": target, "created": now_ms()}
    st.party_invites.append(inv)
    st.notify(target, "PARTY_RECEIVED_INVITATIONS")
    return 200, invite_json(inv)


@route("POST", r"/party/players/" + UUID + r"/invitations/" + UUID + r"/(cancel|accept|reject)")
def party_invite_act(req, pid, iid, act):
    st = req.state
    inv = next((i for i in st.party_invites if i["id"] == iid), None)
    if not inv or req.player not in (inv["from"], inv["to"]) or (act == "accept" and req.player != inv["to"]):
        return 404, {"error": "INVITATION_DOES_NOT_EXIST"}
    st.party_invites.remove(inv)
    st.notify(inv["from"], "PARTY_SENT_INVITATIONS")
    st.notify(inv["to"], "PARTY_RECEIVED_INVITATIONS")
    if act != "accept":
        return 200, {}
    party = st.parties.get(inv["partyId"])
    if not party:
        party = new_party(st, inv["from"])
    if len(party["members"]) >= party["max"]:
        return 409, {"error": "PARTY_IS_FULL"}
    join_party(st, pid, party)
    return 200, party_json(st, party)


# ---- matchmaking (public quick play; private co-op goes through the party) ----
QUEUE_FILL_SECONDS = 10


def match_status(state, pid):
    mid = state.match_of.get(pid)
    m = state.matches.get(mid)
    if not m:
        return {"status": "NONE"}
    if m["state"] == "queue":
        return {"status": "IN_QUEUE", "queue": {"queueId": m["id"], "targetNumPlayers": m["target"],
                                                "members": [member(state, p) for p in m["members"]]}}
    return {"status": "IN_MATCH", "match": {"id": m["id"], "preferredHostPlayerId": m["members"][0],
                                            "targetNumPlayers": m["target"],
                                            "members": [member(state, p) for p in m["members"]]}}


def promote(state, m):
    m["state"] = "match"
    for p in m["members"]:
        state.notify(p, "MATCHMAKING_MATCH")


def tick_matchmaking(state):
    t = time.time()
    for m in list(state.matches.values()):
        if m["state"] == "queue" and t - m["created"] > QUEUE_FILL_SECONDS:
            promote(state, m)


def leave_match(state, pid):
    mid = state.match_of.pop(pid, None)
    m = state.matches.get(mid)
    if m and pid in m["members"]:
        m["members"].remove(pid)
        if not m["members"]:
            del state.matches[mid]
        else:
            for p in m["members"]:
                state.notify(p, "MATCHMAKING_MATCH")


@route("GET", r"/matchmaking/players/" + UUID + r"/matches")
def get_match(req, pid):
    tick_matchmaking(req.state)
    return 200, match_status(req.state, pid)


@route("POST", r"/matchmaking/matches/start")
def mm_start(req):
    st = req.state
    j = req.json()
    mates = set((st.parties.get(st.party_of.get(req.player)) or {}).get("members", [])) | {req.player}
    pids = [p for p in j.get("playerIds", []) if p in mates]
    if req.player not in pids:
        pids.insert(0, req.player)
    target = int(j.get("targetNumPlayers") or 4)
    if target <= 0:
        target = 4
    ident = j.get("targetIdentifier") or ""
    for p in pids:
        leave_match(st, p)
    # join an open queue with the same identifier/size that still has room
    m = next((m for m in st.matches.values() if m["state"] == "queue" and m["ident"] == ident
              and m["target"] == target and len(m["members"]) + len(pids) <= target), None)
    if not m:
        m = {"id": str(uuid.uuid4()), "state": "queue", "ident": ident, "target": target, "members": [], "created": time.time()}
        st.matches[m["id"]] = m
    m["members"] += pids
    for p in pids:
        st.match_of[p] = m["id"]
    if len(m["members"]) >= target:
        promote(st, m)
    else:
        for p in m["members"]:
            st.notify(p, "MATCHMAKING_MATCH")
    return 200, match_status(st, req.player or pids[0])


@route("POST", r"/matchmaking/matches/rematch")
def mm_rematch(req):
    st = req.state
    j = req.json()
    m = st.matches.get(j.get("matchId"))
    if m and req.player in m["members"]:
        m["state"] = "queue"
        m["created"] = time.time()
        m["target"] = int(j.get("targetNumPlayers") or m["target"])
        if len(m["members"]) >= m["target"]:
            promote(st, m)
    return 200, match_status(st, req.player)


@route("POST", r"/matchmaking/matches/force")
def mm_force(req):
    st = req.state
    m = st.matches.get(st.match_of.get(req.player))
    if m and m["state"] == "queue":
        promote(st, m)
    return 200, match_status(st, req.player)


@route("POST", r"/matchmaking/matches/leave")
def mm_leave(req):
    mates = set((req.state.parties.get(req.state.party_of.get(req.player)) or {}).get("members", [])) | {req.player}
    for p in req.json().get("playerIds", []):
        if p in mates:
            leave_match(req.state, p)
    return 200, {"status": "NONE"}


# ---- moderation / presence / challenges / misc -----------------------
@route("GET", r"/moderation/moderation/player/[A-Z0-9]+/" + UUID + r"/active")
def moderation(req, pid):
    return 200, []


@route("POST", r"/moderation(/report-ugc)?")
def report(req, _):
    return 200, {}


@route("GET", r"/playerPresence/players(/.*)?")
def presence_get(req, _):
    return 200, []


@route("POST", r"/playerPresence/players(/.*)?")
def presence_set(req, _):
    return 200, {}


# ---- daily challenges ("daily quests") ----
CH = r"/challenges/challenges"


@route("GET", CH + r"/players/" + UUID + r"/currentDailyChallenges")
def daily(req, pid):
    p = req.state.players.get(pid)
    if not p:
        return 404, {"error": "PLAYER_DOES_NOT_EXIST"}
    d = challenges.today(p, pid)
    req.state.save()
    return 200, challenges.response(pid, d)


@route("POST", CH + r"/players/" + UUID + r"/challenges/([A-Za-z0-9_-]+)")
def daily_step(req, pid, cid):
    p = req.state.players.get(pid)
    if not p or req.player != pid:
        return 403, {"error": "UNAUTHORIZED"}
    xp = challenges.set_steps(p, pid, cid, req.json().get("stepsCompleted", 0))
    if xp:
        p["xp"] = p.get("xp", 0) + xp
        log.info("daily challenge %s done by %s: +%d xp", cid, p.get("name"), xp)
    req.state.save()
    return 200, challenges.response(pid, challenges.today(p, pid))


@route("POST", CH + r"/forceResetPlayerDailyChallenges")
def daily_reroll(req):
    j = req.json()
    pid = req.player
    p = req.state.players.get(pid)
    d = challenges.reroll(p, pid, j.get("challengeIds") or [])
    req.state.save()
    return 200, challenges.response(pid, d)


@route("POST", CH + r"/expiringPlayerDailyChallenges")
def daily_expire(req):
    return 200, {}


@route("GET", r"/leaderboards/.*")
def leaderboards(req):
    return 200, []


@route("POST", r"/leaderboards/.*")
def leaderboards_post(req):
    return 200, {}


# ---- player progression (minimal; campaign progress is also kept client-side) ----
PP = r"/player-progression"


@route("GET", PP + r"/playerProgression/players/" + UUID + r"/inventory")
def inventory(req, pid):
    p = req.state.players.get(pid, {})
    return 200, {"playerId": pid, "inventory": p.get("inventory", []), "characters": p.get("characters", [])}


@route("GET", PP + r"/players/" + UUID + r"/campaigns")
def player_campaigns(req, pid):
    p = req.state.players.get(pid, {})
    return 200, {"playerId": pid, "scores": p.get("scores", []), "unlockedLevels": p.get("unlockedLevels", [])}


def xp_json(state, pid):
    p = state.players.get(pid, {})
    return {"playerId": pid, "userName": p.get("name", ""), "avatarUrl": "", "profileMetadata": "",
            "currentSeasonLevel": p.get("level", 1), "currentSeasonXp": p.get("xp", 0),
            "currentGlobalLevel": p.get("level", 1), "currentGlobalXp": p.get("xp", 0)}


@route("GET", PP + r"/playerProgression/players/" + UUID + r"/progression")
def progression(req, pid):
    return 200, xp_json(req.state, pid)


@route("GET", PP + r"/playerProgression/batchPlayerProgression")
def batch_progression(req):
    return 200, [xp_json(req.state, p) for p in req.query.get("playerIds", []) if p in req.state.players]


@route("GET", PP + r"/(itemSets|ugcEvents/experience|campaignLevels)")
def pp_lists(req, _):
    return 200, []


@route("GET", PP + r"/seasonReward/rewardTrack")
def reward_track(req):
    return 200, {"seasonId": "revival", "seasonLevels": [], "seasonFinish": now_ms() + 365 * 86400000}


@route("GET", PP + r"/players/" + UUID + r"/(playedLevels|favouriteLevels)")
def played(req, pid, _):
    return 200, []


@route("POST", PP + r"/.*")
def pp_post(req):
    return 200, {"playerId": req.player}


# ---- community levels (UGC) / telemetry / twitch: not revived, answer empty ----
@route("GET", r"/(surgeon-ugc|ugc-metadata)/.*")
def ugc_get(req, _):
    return 200, []


@route("POST", r"/(surgeon-ugc|ugc-metadata|rich-presence|telemetry|twitch)/.*")
def misc_post(req, _):
    return 200, {}
