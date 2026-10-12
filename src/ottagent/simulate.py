"""Outcome simulator: what viewers do in the 10 days after the replay evening.

It reads hidden viewer propensities (_simulator/latent.json) that the agent never sees, and the
agent's PUBLISHED actions. Holdout viewers and viewers the agent did not act on get no treatment
effect. The effect sizes below are *assumptions of this synthetic world*; the point of the replay is
that the measurement code recovers them honestly, not that they describe real viewers.
"""
import json
import os
import random

from .config import iso

DAY = 86_400
EFFECT = {
    "surface_play_lift": 0.10,       # extra daily play probability after a home-page row / hero in the right dialect
    "surface_complete_lift": 0.08,   # extra completion probability when the served short-form title is played
    "offer_purchase_lift": 0.04,     # extra purchase probability on the day of an in-app plan offer
    "message_open_lift": 0.10,       # extra app-open probability on the day a push/WhatsApp lands
}


def simulate(store, pack_dir, start_ts, days=10, seed=11):
    rng = random.Random(seed)
    latent = json.load(open(os.path.join(pack_dir, "_simulator", "latent.json"), encoding="utf-8"))
    catalogue = store.titles()
    viewers = [r["viewer_id"] for r in store.db.execute("SELECT DISTINCT viewer_id FROM decisions ORDER BY viewer_id")]
    n_events = 0
    seq = [0]

    def emit(vid, etype, ts, dialect, payload, late=False):
        nonlocal n_events
        seq[0] += 1
        recv = ts + (rng.randint(2 * DAY, 3 * DAY) if late else rng.randint(1, 60))
        store.ingest_event({"event_id": f"S{seq[0]:07d}", "viewer_id": vid, "type": etype,
                            "device_ts": iso(ts), "received_ts": iso(recv), "app_dialect": dialect,
                            "payload": payload})
        n_events += 1

    for vid in viewers:
        lat = latent[vid]
        eng = lat["engagement"]
        dialect = lat["app_dialect_final"]
        acts = store.actions_for(vid)
        surface = [a for a in acts if a["channel"] in ("HOME_PAGE", "HERO_SLOT")]
        offers = [a for a in acts if a["channel"] == "IN_APP"]
        msgs = [a for a in acts if a["channel"] in ("PUSH", "WHATSAPP")]
        served = [c.split(":", 1)[1] for a in surface for c in a["content"]]
        right_dialect = any(a["dialect"] == dialect for a in surface)
        pool = [t for t in catalogue.values() if dialect in t["dialects"] and not t["quarantined"]]
        progress = {}
        completions = len([1 for _ in store.db.execute(
            "SELECT 1 FROM events WHERE viewer_id=? AND type='episode_complete'", (vid,))])
        paid = store.db.execute("SELECT COUNT(*) c FROM events WHERE viewer_id=? AND type='purchase'", (vid,)).fetchone()["c"] > 0
        for day in range(days):
            day_start = start_ts + day * DAY
            p_open = 0.08 + 0.55 * eng
            if any(abs(_ts(m["send_at"]) - day_start) < DAY for m in msgs):
                p_open += EFFECT["message_open_lift"]
            if rng.random() > p_open:
                continue
            t = day_start + rng.uniform(1800, 5 * 3600)
            emit(vid, "app_open", t, dialect, {})
            p_play = 0.40 + 0.30 * eng + (EFFECT["surface_play_lift"] if served and right_dialect and day < 4 else 0)
            if rng.random() < p_play and pool:
                use_served = served and right_dialect and rng.random() < 0.55
                tid = rng.choice(served) if use_served else rng.choice(pool)["title_id"]
                title = catalogue[tid]
                ep = progress.get(tid, 1)
                emit(vid, "play_start", t + 30, dialect, {"title_id": tid, "episode": ep, "dialect": dialect})
                p_done = 0.30 + 0.40 * eng + (EFFECT["surface_complete_lift"] if use_served else 0)
                if rng.random() < p_done:
                    progress[tid] = ep + 1
                    completions += 1
                    emit(vid, "episode_complete", t + 30 + title["episode_minutes"] * 60, dialect,
                         {"title_id": tid, "episode": ep, "watch_pct": round(rng.uniform(0.70, 1.0), 2), "dialect": dialect},
                         late=rng.random() < 0.03)
            if not paid and completions:
                p_buy = 0.006 + 0.02 * eng + (EFFECT["offer_purchase_lift"] if offers and day == 0 else 0)
                if rng.random() < p_buy:
                    paid = True
                    emit(vid, "purchase", t + 600, dialect, {"plan": "monthly", "amount_inr": 99, "renewal": False})
    return {"viewers_simulated": len(viewers), "events_generated": n_events, "effects_assumed": EFFECT}


def _ts(s):
    from .config import parse
    return parse(s)
