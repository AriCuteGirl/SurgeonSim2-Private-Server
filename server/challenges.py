"""Daily challenges (the game's "daily quests"): 3 per player per UTC day.

Shape from Services/ChallengeApi.cs; "metadata" is a JSON ChallengeConfig
(LevelStatisticType: 0 FinishMatch, 1 FinishWithStrangers, 2 WinMatch, 3 RateMatch,
 4 TransplantOrgan, 5 TransplantLimb, 6 UseSyringe(ml); RequiredLimbCategory 1 Leg, 2 Arm).
"""
import datetime
import hashlib
import json

POOL = {
    "finish":      dict(type=0, name="FINISH_QUICKPLAY_MATCH", desc="FINISH_QUICKPLAY_MATCH_DESCRIPTION", steps=3, xp=300),
    "bffs":        dict(type=0, name="FINISH_QUICKPLAY_MATCH_WITH_2", desc="FINISH_QUICKPLAY_MATCH_WITH_N_DESCRIPTION", steps=2, xp=450, party=2),
    "crowd":       dict(type=0, name="FINISH_QUICKPLAY_MATCH_WITH_3", desc="FINISH_QUICKPLAY_MATCH_WITH_N_DESCRIPTION", steps=2, xp=500, party=3),
    "win":         dict(type=2, name="WIN_QUICKPLAY_MATCH", desc="WIN_QUICKPLAY_MATCH_DESCRIPTION", steps=2, xp=400),
    "limbs":       dict(type=5, name="TRANSPLANT_LIMBS", desc="TRANSPLANT_LIMBS_DESCRIPTION", steps=5, xp=350),
    "legs":        dict(type=5, name="TRANSPLANT_LEGS", desc="TRANSPLANT_SPECIFIC_LIMBS_DESCRIPTION", steps=3, xp=350, limb=1),
    "arms":        dict(type=5, name="TRANSPLANT_ARMS", desc="TRANSPLANT_SPECIFIC_LIMBS_DESCRIPTION", steps=3, xp=350, limb=2),
    "organs":      dict(type=4, name="TRANSPLANT_ORGANS", desc="TRANSPLANT_ORGANS_DESCRIPTION", steps=5, xp=350),
    "blood":       dict(type=6, name="INJECT_BLOOD", desc="INJECT_BLOOD_DESCRIPTION", steps=500, xp=300),
}
KEYS = sorted(POOL)


def day_bounds():
    now = datetime.datetime.now(datetime.timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + datetime.timedelta(days=1)
    return start.strftime("%Y%m%d"), int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def metadata(key):
    c = POOL[key]
    cfg = {"LevelStatisticType": c["type"], "NameLocalisationKey": c["name"], "DescriptionLocalisationKey": c["desc"]}
    if "party" in c:
        cfg["MinimumPartySize"] = c["party"]
    if "limb" in c:
        cfg["RequiredLimbCategory"] = c["limb"]
    return json.dumps(cfg)


def _pick(pid, day, exclude, salt=0):
    """Deterministic pick so the same player gets the same set all day."""
    ranked = sorted((k for k in KEYS if k not in exclude),
                    key=lambda k: hashlib.sha1(f"{pid}{day}{k}{salt}".encode()).hexdigest())
    return ranked[0]


def today(player, pid):
    """Return (and lazily create) today's challenge set stored on the player record."""
    day, created, expires = day_bounds()
    d = player.get("daily")
    if not d or d.get("day") != day:
        keys = []
        for slot in range(3):
            keys.append(_pick(pid, day, keys))
        # slot index is part of the id: the client sorts challenges by id
        d = {"day": day, "created": created, "expires": expires,
             "slots": [{"id": f"{day}-{i}-{k}", "key": k, "steps": 0, "paid": False} for i, k in enumerate(keys)]}
        player["daily"] = d
    return d


def response(pid, d):
    return {"playerId": pid, "createdAt": d["created"], "expiresAt": d["expires"],
            "challenges": [{"challengeId": s["id"], "metadata": metadata(s["key"]),
                            "totalNumberOfSteps": POOL[s["key"]]["steps"], "stepsCompleted": s["steps"],
                            "xpGain": POOL[s["key"]]["xp"]} for s in d["slots"]]}


def set_steps(player, pid, challenge_id, steps):
    """Store progress; returns XP earned now (paid once per challenge)."""
    d = today(player, pid)
    for s in d["slots"]:
        if s["id"] == challenge_id:
            total = POOL[s["key"]]["steps"]
            s["steps"] = max(s["steps"], min(int(steps), total))
            if s["steps"] >= total and not s["paid"]:
                s["paid"] = True
                return POOL[s["key"]]["xp"]
    return 0


def reroll(player, pid, challenge_ids):
    d = today(player, pid)
    used = [s["key"] for s in d["slots"]]
    for i, s in enumerate(d["slots"]):
        if s["id"] in challenge_ids and not s["paid"]:
            k = _pick(pid, d["day"], used, salt=len(used))
            used.append(k)
            d["slots"][i] = {"id": f"{d['day']}-{i}-{k}", "key": k, "steps": 0, "paid": False}
    return d
