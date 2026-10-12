"""Durable state: one SQLite file holds raw evidence and every per-viewer record.

Raw evidence (events, profile rows, catalogue) is append-only and keeps its original source
fields. Agent records (goals, decisions, actions, outcomes, learnings) reference evidence by id.
Nothing the agent writes is ever read back as if it were evidence about the viewer.
"""
import csv
import json
import os
import sqlite3
import statistics

from .config import parse

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, viewer_id TEXT, type TEXT, device_ts REAL, received_ts REAL,
  app_dialect TEXT, payload TEXT, dup_count INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ev_viewer ON events(viewer_id, received_ts);
CREATE TABLE IF NOT EXISTS profile_rows (
  row_no INTEGER PRIMARY KEY, viewer_id TEXT, data TEXT, updated_at REAL);
CREATE INDEX IF NOT EXISTS prof_viewer ON profile_rows(viewer_id);
CREATE TABLE IF NOT EXISTS titles (title_id TEXT PRIMARY KEY, data TEXT, quarantined INTEGER DEFAULT 0, quarantine_reason TEXT);
CREATE TABLE IF NOT EXISTS goal_rules (goal_id TEXT, version INTEGER, data TEXT, effective_at REAL, PRIMARY KEY(goal_id, version));
CREATE TABLE IF NOT EXISTS triggers (trigger_id TEXT PRIMARY KEY, viewer_id TEXT, first_seen REAL, decision_id TEXT, deliveries INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS goals (
  goal_instance_id TEXT PRIMARY KEY, viewer_id TEXT, goal_id TEXT, status TEXT, opened_at REAL, deadline REAL,
  decision_id TEXT, arm TEXT, success_rule_version INTEGER, closed_at REAL, verdict TEXT, data TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_goal ON goals(viewer_id) WHERE status = 'ACTIVE';
CREATE TABLE IF NOT EXISTS decisions (decision_id TEXT PRIMARY KEY, viewer_id TEXT, created_at REAL, status TEXT, data TEXT);
CREATE INDEX IF NOT EXISTS dec_viewer ON decisions(viewer_id, created_at);
CREATE TABLE IF NOT EXISTS actions (action_id TEXT PRIMARY KEY, decision_id TEXT, viewer_id TEXT, channel TEXT,
  is_message INTEGER, publish_at REAL, send_at REAL, local_day TEXT, content TEXT, data TEXT);
CREATE INDEX IF NOT EXISTS act_viewer ON actions(viewer_id, publish_at);
CREATE TABLE IF NOT EXISTS outcomes (goal_instance_id TEXT PRIMARY KEY, viewer_id TEXT, judged_at REAL, verdict TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS learnings (id INTEGER PRIMARY KEY AUTOINCREMENT, viewer_id TEXT, ts REAL, kind TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


class Store:
    def __init__(self, path=":memory:"):
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._skew_cache = {}

    # ------------------------------------------------------------------ loading
    def load_pack(self, pack_dir):
        stats = {"events_in_file": 0, "duplicate_event_ids": 0}
        with open(os.path.join(pack_dir, "events.jsonl"), encoding="utf-8") as f:
            for line in f:
                stats["events_in_file"] += 1
                if not self.ingest_event(json.loads(line)):
                    stats["duplicate_event_ids"] += 1
        with open(os.path.join(pack_dir, "profile_snapshot.csv"), encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                self.db.execute("INSERT INTO profile_rows VALUES (?,?,?,?)",
                                (i, row["viewer_id"], json.dumps(row), parse(row["updated_at"])))
        for t in json.load(open(os.path.join(pack_dir, "catalogue.json"), encoding="utf-8")):
            self.db.execute("INSERT OR REPLACE INTO titles(title_id, data) VALUES (?,?)", (t["title_id"], json.dumps(t)))
        for g in json.load(open(os.path.join(pack_dir, "goals.json"), encoding="utf-8")):
            self.db.execute("INSERT OR REPLACE INTO goal_rules VALUES (?,?,?,?)",
                            (g["id"], g["success"]["version"], json.dumps(g), 0))
        self.db.commit()
        return stats

    # ------------------------------------------------------------------ events
    def ingest_event(self, e) -> bool:
        """Idempotent: returns False when the event_id was already stored."""
        cur = self.db.execute(
            "INSERT OR IGNORE INTO events(event_id, viewer_id, type, device_ts, received_ts, app_dialect, payload) "
            "VALUES (?,?,?,?,?,?,?)",
            (e["event_id"], e["viewer_id"], e["type"], parse(e["device_ts"]), parse(e["received_ts"]),
             e.get("app_dialect"), json.dumps(e.get("payload", {}))))
        if cur.rowcount == 0:
            self.db.execute("UPDATE events SET dup_count = dup_count + 1 WHERE event_id = ?", (e["event_id"],))
            return False
        self._skew_cache.pop(e["viewer_id"], None)
        return True

    def device_offset(self, viewer_id, as_of):
        """Median (received - device) for a viewer. A consistent large offset means a wrong device clock;
        single late events do not move the median."""
        key = viewer_id
        rows = self.db.execute("SELECT received_ts - device_ts AS o FROM events WHERE viewer_id=? AND received_ts<=?",
                               (viewer_id, as_of)).fetchall()
        if len(rows) < 3:
            return 0.0, len(rows)
        return statistics.median(r["o"] for r in rows), len(rows)

    def viewer_events(self, viewer_id, as_of, skew_threshold_s=3600):
        """Events received by `as_of`, each with an effective timestamp and how it was derived."""
        med, n = self.device_offset(viewer_id, as_of)
        skewed = abs(med) > skew_threshold_s
        out = []
        for r in self.db.execute("SELECT * FROM events WHERE viewer_id=? AND received_ts<=? ORDER BY device_ts",
                                 (viewer_id, as_of)):
            eff = r["device_ts"] + (med if skewed else 0.0)
            src = "device_ts_skew_corrected" if skewed else "device_ts"
            if eff > r["received_ts"]:          # cannot happen after the server received it
                eff, src = r["received_ts"], "received_ts_clamped"
            out.append({"event_id": r["event_id"], "type": r["type"], "device_ts": r["device_ts"],
                        "received_ts": r["received_ts"], "effective_ts": eff, "ts_source": src,
                        "app_dialect": r["app_dialect"], "payload": json.loads(r["payload"]),
                        "dup_count": r["dup_count"]})
        out.sort(key=lambda x: x["effective_ts"])
        return out, {"device_offset_median_s": round(med, 1), "clock_skew_corrected": skewed, "n": n}

    def event(self, event_id):
        r = self.db.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        return dict(r) if r else None

    # ------------------------------------------------------------------ profile / catalogue / rules
    def profile_rows(self, viewer_id):
        return [dict(json.loads(r["data"]), _row_no=r["row_no"]) for r in
                self.db.execute("SELECT * FROM profile_rows WHERE viewer_id=? ORDER BY updated_at DESC", (viewer_id,))]

    def titles(self):
        return {r["title_id"]: dict(json.loads(r["data"]), quarantined=bool(r["quarantined"]),
                                    quarantine_reason=r["quarantine_reason"])
                for r in self.db.execute("SELECT * FROM titles")}

    def title(self, title_id):
        r = self.db.execute("SELECT * FROM titles WHERE title_id=?", (title_id,)).fetchone()
        if not r:
            return None
        return dict(json.loads(r["data"]), quarantined=bool(r["quarantined"]), quarantine_reason=r["quarantine_reason"])

    def quarantine(self, title_id, reason):
        self.db.execute("UPDATE titles SET quarantined=1, quarantine_reason=? WHERE title_id=?", (reason, title_id))
        self.db.commit()

    def goal_rule(self, goal_id, version=None):
        if version is None:
            r = self.db.execute("SELECT * FROM goal_rules WHERE goal_id=? ORDER BY version DESC LIMIT 1", (goal_id,)).fetchone()
        else:
            r = self.db.execute("SELECT * FROM goal_rules WHERE goal_id=? AND version=?", (goal_id, version)).fetchone()
        return dict(json.loads(r["data"]), _effective_at=r["effective_at"]) if r else None

    def all_goal_rules(self):
        ids = [r["goal_id"] for r in self.db.execute("SELECT DISTINCT goal_id FROM goal_rules ORDER BY goal_id")]
        return {g: self.goal_rule(g) for g in ids}

    def add_goal_rule_version(self, goal_id, success, at):
        g = self.goal_rule(goal_id)
        g["success"] = success
        self.db.execute("INSERT INTO goal_rules VALUES (?,?,?,?)", (goal_id, success["version"], json.dumps(g), at))
        self.db.commit()

    # ------------------------------------------------------------------ triggers
    def seen_trigger(self, trigger_id):
        r = self.db.execute("SELECT * FROM triggers WHERE trigger_id=?", (trigger_id,)).fetchone()
        if r:
            self.db.execute("UPDATE triggers SET deliveries = deliveries + 1 WHERE trigger_id=?", (trigger_id,))
            return dict(r)
        return None

    def record_trigger(self, trigger_id, viewer_id, at, decision_id):
        self.db.execute("INSERT OR REPLACE INTO triggers(trigger_id, viewer_id, first_seen, decision_id) VALUES (?,?,?,?)",
                        (trigger_id, viewer_id, at, decision_id))

    # ------------------------------------------------------------------ goals
    def active_goal(self, viewer_id):
        r = self.db.execute("SELECT * FROM goals WHERE viewer_id=? AND status='ACTIVE'", (viewer_id,)).fetchone()
        return dict(r, data=json.loads(r["data"])) if r else None

    def open_goal(self, gi):
        self.db.execute("INSERT INTO goals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (gi["goal_instance_id"], gi["viewer_id"], gi["goal_id"], "ACTIVE", gi["opened_at"],
                         gi["deadline"], gi["decision_id"], gi["arm"], gi["success_rule_version"], None, None,
                         json.dumps(gi)))

    def close_goal(self, goal_instance_id, status, at, verdict=None, note=None):
        r = self.db.execute("SELECT data FROM goals WHERE goal_instance_id=?", (goal_instance_id,)).fetchone()
        data = json.loads(r["data"])
        if note:
            data.setdefault("notes", []).append(note)
        self.db.execute("UPDATE goals SET status=?, closed_at=?, verdict=?, data=? WHERE goal_instance_id=?",
                        (status, at, verdict, json.dumps(data), goal_instance_id))

    def goals_for(self, viewer_id):
        return [dict(r, data=json.loads(r["data"])) for r in
                self.db.execute("SELECT * FROM goals WHERE viewer_id=? ORDER BY opened_at", (viewer_id,))]

    def goals_due(self, now):
        return [dict(r, data=json.loads(r["data"])) for r in
                self.db.execute("SELECT * FROM goals WHERE status='ACTIVE' AND deadline<=?", (now,))]

    def active_goals_by_goal_id(self, goal_id):
        return [dict(r) for r in self.db.execute("SELECT * FROM goals WHERE goal_id=? AND status IN ('ACTIVE')", (goal_id,))]

    # ------------------------------------------------------------------ decisions / actions / outcomes / learnings
    def save_decision(self, d):
        self.db.execute("INSERT INTO decisions VALUES (?,?,?,?,?)",
                        (d["decision_id"], d["viewer_id"], d["_created_ts"], d["status"], json.dumps(d)))

    def decisions_for(self, viewer_id, as_of=None):
        q = "SELECT data FROM decisions WHERE viewer_id=?" + (" AND created_at<=?" if as_of else "") + " ORDER BY created_at"
        args = (viewer_id, as_of) if as_of else (viewer_id,)
        return [json.loads(r["data"]) for r in self.db.execute(q, args)]

    def save_action(self, a):
        self.db.execute("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (a["action_id"], a["decision_id"], a["viewer_id"], a["channel"], int(a["is_message"]),
                         a["publish_at"], a.get("send_at"), a.get("local_day"), json.dumps(a.get("content", [])),
                         json.dumps(a)))

    def actions_for(self, viewer_id, since=None):
        q = "SELECT data FROM actions WHERE viewer_id=?" + (" AND publish_at>=?" if since else "") + " ORDER BY publish_at"
        args = (viewer_id, since) if since else (viewer_id,)
        return [json.loads(r["data"]) for r in self.db.execute(q, args)]

    def messages_on_local_day(self, viewer_id, local_day):
        return self.db.execute("SELECT COUNT(*) c FROM actions WHERE viewer_id=? AND is_message=1 AND local_day=?",
                               (viewer_id, local_day)).fetchone()["c"]

    def save_outcome(self, o):
        self.db.execute("INSERT OR REPLACE INTO outcomes VALUES (?,?,?,?,?)",
                        (o["goal_instance_id"], o["viewer_id"], o["judged_at_ts"], o["verdict"], json.dumps(o)))

    def outcomes_for(self, viewer_id):
        return [json.loads(r["data"]) for r in self.db.execute("SELECT data FROM outcomes WHERE viewer_id=?", (viewer_id,))]

    def add_learning(self, viewer_id, ts, kind, data):
        self.db.execute("INSERT INTO learnings(viewer_id, ts, kind, data) VALUES (?,?,?,?)",
                        (viewer_id, ts, kind, json.dumps(data)))

    def learnings_for(self, viewer_id, as_of=None):
        q = "SELECT * FROM learnings WHERE viewer_id=?" + (" AND ts<=?" if as_of else "") + " ORDER BY ts"
        args = (viewer_id, as_of) if as_of else (viewer_id,)
        return [dict(kind=r["kind"], ts=r["ts"], **json.loads(r["data"])) for r in self.db.execute(q, args)]

    def commit(self):
        self.db.commit()
