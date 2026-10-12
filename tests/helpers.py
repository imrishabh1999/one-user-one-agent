"""Tiny hand-built worlds for tests: every fact in them is visible in the test itself."""
from datetime import datetime

from ottagent.agent import Agent
from ottagent.catalogues import GOALS
from ottagent.config import IST, Config, iso
from ottagent.datagen import is_holdout
from ottagent.deps import Environment, MockLLM
from ottagent.store import Store
import json

T0 = datetime(2026, 10, 1, 19, 0, tzinfo=IST).timestamp()   # 19:00 IST, outside quiet hours
DAY = 86_400


def title(tid, dialects, minutes=5, premium=False, desc=None, genre="drama", group=None, fmt="micro", eps=20):
    return {"title_id": tid, "variant_group": group or f"VG-{tid}", "name": tid, "format": fmt, "genre": genre,
            "episodes": eps, "episode_minutes": minutes, "premium": premium, "popularity": 0.5,
            "available_from": "2026-01-01T00:00:00Z", "available_to": None, "dialects": dialects,
            "language": "hi", "description": desc or f"A {genre} title."}


DEFAULT_TITLES = ([title(f"T1{i:02d}", ["d1"]) for i in range(8)] + [title(f"T3{i:02d}", ["d3"]) for i in range(8)]
                  + [title(f"T9{i:02d}", ["d1", "d3"], premium=True) for i in range(8)])


class World:
    def __init__(self, titles=None, cfg=None):
        self.cfg = cfg or Config()
        self.s = Store()
        self.n = 0
        for g in GOALS:
            self.s.db.execute("INSERT INTO goal_rules VALUES (?,?,?,?)", (g["id"], 1, json.dumps(g), 0))
        for t in (titles or DEFAULT_TITLES):
            self.s.db.execute("INSERT INTO titles(title_id, data) VALUES (?,?)", (t["title_id"], json.dumps(t)))
        # a background viewer so every real event type has been observed (goals are measurable)
        for typ in ("app_open", "sign_up", "play_start", "episode_complete", "purchase", "search"):
            self.event("V-BG", typ, T0 - 20 * DAY, payload={"title_id": "T100", "episode": 1, "watch_pct": 1.0})
        self.env = Environment()

    def eid(self):
        self.n += 1
        return f"E{self.n:05d}"

    def event(self, vid, typ, ts, recv=None, dialect="d1", payload=None, event_id=None):
        e = {"event_id": event_id or self.eid(), "viewer_id": vid, "type": typ, "device_ts": iso(ts),
             "received_ts": iso(recv if recv is not None else ts + 5), "app_dialect": dialect, "payload": payload or {}}
        self.s.ingest_event(e)
        return e

    def profile(self, vid, status="never_paid", dialect="d1", push=1, wa=1, signup=None, updated=None, expires=""):
        row = {"viewer_id": vid, "signup_date": iso(signup or T0 - 60 * DAY), "subscription_status": status,
               "sub_expires_at": expires, "preferred_dialect": dialect, "language": "hi", "consent_push": push,
               "consent_whatsapp": wa, "updated_at": iso(updated or T0 - 2 * DAY)}
        n = self.s.db.execute("SELECT COUNT(*) c FROM profile_rows").fetchone()["c"]
        self.s.db.execute("INSERT INTO profile_rows VALUES (?,?,?,?)", (n, vid, json.dumps(row), T0))
        return row

    def agent(self, provider=None):
        self.a = Agent(self.s, self.cfg, self.env, provider or MockLLM())
        return self.a

    def trigger(self, vid, ts, recv=None, dialect="d1", trigger_id=None, event_id=None):
        e = {"event_id": event_id or self.eid(), "viewer_id": vid, "type": "app_open", "device_ts": iso(ts),
             "received_ts": iso(recv if recv is not None else ts + 3), "app_dialect": dialect, "payload": {}}
        return {"kind": "trigger", "trigger_id": trigger_id or f"TR-{e['event_id']}", "event": e}

    def watched(self, vid, n=2, dialect="d1", start=None, prefix="T1"):
        t = start or T0 - 10 * DAY
        for i in range(n):
            self.event(vid, "app_open", t + i * DAY, dialect=dialect)
            self.event(vid, "play_start", t + i * DAY + 60, dialect=dialect,
                       payload={"title_id": f"{prefix}0{i}", "episode": 1, "dialect": dialect})
            self.event(vid, "episode_complete", t + i * DAY + 600, dialect=dialect,
                       payload={"title_id": f"{prefix}0{i}", "episode": 1, "watch_pct": 0.95, "dialect": dialect})


def viewer(arm="treatment", start=0):
    """A viewer id that lands in the requested arm."""
    cfg = Config()
    i = start
    while True:
        vid = f"V-T{i:04d}"
        if is_holdout(vid, cfg) == (arm == "holdout"):
            return vid
        i += 1
