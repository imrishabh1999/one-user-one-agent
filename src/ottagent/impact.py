"""Measure the agent's effect against the randomized holdout (intent-to-treat), and show why the
simpler comparisons mislead.

Population: viewers with at least one fresh (in-session) app_open during the replay. Whether a viewer
opens the app does not depend on their arm, so the population is defined before treatment.
Arm: a salted hash of viewer_id (fixed before the replay), 10% holdout.
ITT compares *all* treatment-arm viewers with *all* holdout viewers, including treatment viewers the
agent decided not to act on. That is the effect of deploying the agent, which is the decision we
actually face.
"""
import csv
import json
import math
import os

DAY = 86_400


def _rate(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def wilson(p, n, z=1.96):
    if n == 0:
        return 0.0, 1.0
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def diff_ci(a, b):
    """Difference of two proportions a-b with a Newcombe (Wilson-score) 95% CI and a two-proportion z-test.
    Newcombe rather than bootstrap/Wald: it stays honest when a small arm has zero or very few events."""
    p1, p2, n1, n2 = _rate(a), _rate(b), len(a), len(b)
    d = p1 - p2
    l1, u1 = wilson(p1, n1)
    l2, u2 = wilson(p2, n2)
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    pp = (sum(a) + sum(b)) / (n1 + n2)
    se = math.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2)) if 0 < pp < 1 else float("nan")
    z = (p1 - p2) / se if se and se == se and se > 0 else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))
    return {"treat_rate": round(p1, 4), "control_rate": round(p2, 4), "n_treat": n1, "n_control": n2,
            "diff_pp": round(100 * d, 2), "ci95_pp": [round(100 * lo, 2), round(100 * hi, 2)], "p_value": round(p, 4)}


def build_population(store, decisions):
    first = {}
    for d in decisions:
        if d["trigger"].get("event") != "app_open" or not d.get("in_session"):
            continue
        if d["viewer_id"] not in first:
            first[d["viewer_id"]] = d
    served = {d["viewer_id"] for d in decisions if d["status"] == "PUBLISHED"}
    rows = []
    for vid, d in first.items():
        t0 = d["_created_ts"]
        ev = store.db.execute("SELECT type, device_ts, received_ts, payload FROM events WHERE viewer_id=?", (vid,)).fetchall()
        pre_events = sum(1 for e in ev if e["received_ts"] < t0 - 60)
        complete_3d = any(e["type"] == "episode_complete" and t0 <= e["device_ts"] <= t0 + 3 * DAY
                          and json.loads(e["payload"]).get("watch_pct", 0) >= 0.9 for e in ev)
        purchase_7d = any(e["type"] == "purchase" and t0 <= e["device_ts"] <= t0 + 7 * DAY for e in ev)
        sub = (d.get("facts") or {}).get("subscription", {}).get("value")
        rows.append({"viewer_id": vid, "arm": d["arm"], "served": vid in served, "pre_events": pre_events,
                     "complete_3d": int(complete_3d), "purchase_7d": int(purchase_7d),
                     "never_paid_at_start": sub in ("trial", "never_paid"), "first_decision": d["decision_id"]})
    return rows


def first_goal_success(decisions, outcomes):
    """Per viewer: verdict of the first goal opened in the replay (both arms open goals; holdout ones are shadow goals)."""
    by_gi = {o["goal_instance_id"]: o for o in outcomes}
    seen, rows = set(), []
    for d in decisions:
        g = d.get("goal")
        if not g or g.get("continuing") or d["viewer_id"] in seen or not g.get("instance"):
            continue
        seen.add(d["viewer_id"])
        o = by_gi.get(g["instance"])
        if o:
            rows.append({"viewer_id": d["viewer_id"], "arm": d["arm"], "goal": g["id"], "verdict": o["verdict"]})
    return rows


def pilot_analysis(pack_dir):
    rows = list(csv.DictReader(open(os.path.join(pack_dir, "pilot_results.csv"), encoding="utf-8")))
    conv = lambda rs: [int(r["converted_7d"]) for r in rs]
    t = [r for r in rows if r["arm"] == "treatment"]
    h = [r for r in rows if r["arm"] == "holdout"]
    served = [r for r in rows if r["served"] == "1"]
    rest = [r for r in rows if r["served"] != "1"]
    itt = diff_ci(conv(t), conv(h))
    naive = diff_ci(conv(served), conv(rest))
    share = len([r for r in t if r["served"] == "1"]) / len(t)
    opened_t = [r for r in t if r["opened_app"] == "1"]
    opened_h = [r for r in h if r["opened_app"] == "1"]
    return {"itt": itt, "naive_served_vs_rest": naive, "served_share_in_treatment": round(share, 3),
            "effect_on_served_cace_pp": round(itt["diff_pp"] / share, 2),
            "effect_on_served_cace_ci_pp": [round(itt["ci95_pp"][0] / share, 2), round(itt["ci95_pp"][1] / share, 2)],
            "openers_only_treat_vs_holdout": diff_ci(conv(opened_t), conv(opened_h)),
            "claimed": open(os.path.join(pack_dir, "pilot_internal_report.md"), encoding="utf-8").read().strip()}


def analyse(store, decisions, outcomes, pack_dir):
    pop = build_population(store, decisions)
    T = [r for r in pop if r["arm"] == "treatment"]
    H = [r for r in pop if r["arm"] == "holdout"]
    served = [r for r in pop if r["served"]]
    unserved = [r for r in pop if not r["served"]]
    res = {"population": len(pop), "treatment": len(T), "holdout": len(H),
           "served_share_in_treatment": round(len([r for r in T if r["served"]]) / max(1, len(T)), 3),
           "balance_pre_events": {"treatment": round(sum(r["pre_events"] for r in T) / len(T), 2),
                                  "holdout": round(sum(r["pre_events"] for r in H) / len(H), 2),
                                  "served": round(sum(r["pre_events"] for r in served) / max(1, len(served)), 2),
                                  "unserved": round(sum(r["pre_events"] for r in unserved) / max(1, len(unserved)), 2)},
           "itt_complete_3d": diff_ci([r["complete_3d"] for r in T], [r["complete_3d"] for r in H]),
           "itt_purchase_7d_never_paid": diff_ci([r["purchase_7d"] for r in T if r["never_paid_at_start"]],
                                                 [r["purchase_7d"] for r in H if r["never_paid_at_start"]]),
           "naive_served_vs_unserved_complete_3d": diff_ci([r["complete_3d"] for r in served],
                                                           [r["complete_3d"] for r in unserved])}
    gs = first_goal_success(decisions, outcomes)
    judged = [r for r in gs if r["verdict"] in ("SUCCEEDED", "FAILED")]
    res["itt_first_goal_success"] = diff_ci([int(r["verdict"] == "SUCCEEDED") for r in judged if r["arm"] == "treatment"],
                                            [int(r["verdict"] == "SUCCEEDED") for r in judged if r["arm"] == "holdout"])
    res["first_goal_inconclusive"] = len(gs) - len(judged)
    by_goal = {}
    for r in judged:
        by_goal.setdefault(r["goal"], {"treatment": [], "holdout": []})[r["arm"]].append(int(r["verdict"] == "SUCCEEDED"))
    res["first_goal_success_by_goal"] = {g: {a: [sum(v), len(v)] for a, v in x.items()} for g, x in sorted(by_goal.items())}
    res["pilot"] = pilot_analysis(pack_dir)
    return res
