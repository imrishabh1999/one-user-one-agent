"""Close the loop: judge each goal from attributable signals only.

A goal is judged once its deadline plus a grace period for late events has passed. Only events that
(a) belong to this viewer, (b) happened inside [opened_at, deadline] by effective time, and (c) reached
the server before deadline + grace count. Events arriving after that are reported, not counted.

Verdicts
  SUCCEEDED     a qualifying success event exists
  FAILED        no qualifying event, the signal is measurable and the feed is complete for the window
  INCONCLUSIVE  the signal is unmeasurable, the feed for the window is incomplete, the goal premise was
                false when the decision was made, or the goal was superseded before its deadline
Attribution (only for SUCCEEDED): via_served_content / goal_met_other_content / holdout_no_action.
"""
from .config import iso, local_day

DAY = 86_400


def qualifying_events(store, g, rule, now, cfg):
    data = g["data"]
    events, _ = store.viewer_events(g["viewer_id"], now, cfg.clock_skew_threshold_s)
    s = rule["success"]
    lo, hi = g["opened_at"], g["deadline"]
    counted, late = [], []
    open_days = set()
    for e in events:
        if e["type"] not in s["event_types"] or not (lo <= e["effective_ts"] <= hi):
            continue
        p = e["payload"]
        if s.get("min_watch_pct") is not None and p.get("watch_pct", 0) < s["min_watch_pct"]:
            continue
        if s.get("distinct_episode") and [p.get("title_id"), p.get("episode")] in data.get("baseline_completed", []):
            continue
        if s.get("last_episode") and not (p.get("title_id") == data.get("series_id") and p.get("episode") == data.get("series_last_ep")):
            continue
        if s.get("later_local_day") and local_day(e["effective_ts"]) == local_day(lo):
            continue
        if s.get("other_dialect") and p.get("dialect") == data.get("dialect"):
            continue
        if e["received_ts"] > hi + cfg.judge_grace_s:
            late.append(e["event_id"])
            continue
        counted.append(e)
        open_days.add(local_day(e["effective_ts"]))
    if s.get("distinct_days") and len(open_days) < s["distinct_days"]:
        counted = []
    return counted, late


def judge_goal(store, g, now, cfg, measurable, feed_complete_until):
    rule_now = store.goal_rule(g["goal_id"])
    rule_open = store.goal_rule(g["goal_id"], g["success_rule_version"]) or rule_now
    out = {"goal_instance_id": g["goal_instance_id"], "viewer_id": g["viewer_id"], "goal_id": g["goal_id"],
           "decision_id": g["decision_id"], "arm": g["arm"], "opened_at": iso(g["opened_at"]),
           "deadline": iso(g["deadline"]), "judged_at": iso(now), "judged_at_ts": now,
           "rule_version_at_open": rule_open["success"]["version"], "rule_version_used": rule_now["success"]["version"]}
    if measurable.get(g["goal_id"]):
        out.update(verdict="INCONCLUSIVE", reason=measurable[g["goal_id"]], evidence=[])
        return out
    if feed_complete_until < g["deadline"] + cfg.judge_grace_s:
        out.update(verdict="INCONCLUSIVE", reason="event feed not complete for the window yet", evidence=[])
        return out
    counted, late = qualifying_events(store, g, rule_now, now, cfg)
    if rule_open["success"]["version"] != rule_now["success"]["version"]:
        old, _ = qualifying_events(store, g, rule_open, now, cfg)
        out["verdict_under_rule_at_open"] = "SUCCEEDED" if old else "FAILED"
    out["late_events_not_counted"] = late
    if counted:
        first = counted[0]
        served = g["data"].get("content_titles", [])
        if g["arm"] == "holdout":
            attribution = "holdout_no_action"
        elif not g["data"].get("acted"):
            attribution = "no_action_taken"
        elif first["payload"].get("title_id") in served or g["data"].get("action") in ("IN_APP", "PUSH", "WHATSAPP"):
            attribution = "via_served_content" if first["payload"].get("title_id") in served else "after_served_message"
        else:
            attribution = "goal_met_other_content"
        out.update(verdict="SUCCEEDED", reason=f"{first['type']} at {iso(first['effective_ts'])}",
                   evidence=[f"event:{e['event_id']}" for e in counted[:3]], attribution=attribution)
    else:
        out.update(verdict="FAILED", reason="no qualifying success event inside the window", evidence=[])
    if "verdict_under_rule_at_open" in out:
        out["verdict_changed_by_rule_correction"] = out["verdict_under_rule_at_open"] != out["verdict"]
    return out


def learn_from(store, outcome, goal_row):
    """Feed the verdict back into the viewer's durable state."""
    d = goal_row["data"]
    vid, ts = outcome["viewer_id"], outcome["judged_at_ts"]
    if outcome["verdict"] == "SUCCEEDED":
        store.add_learning(vid, ts, "what_worked", {"goal": outcome["goal_id"], "action": d.get("action"),
                                                    "dialect": d.get("dialect"), "attribution": outcome.get("attribution"),
                                                    "decision_id": outcome["decision_id"]})
        if d.get("dialect"):
            store.add_learning(vid, ts, "dialect_confirmed", {"dialect": d.get("dialect"), "by": outcome["evidence"][:1]})
    elif outcome["verdict"] == "FAILED":
        if d.get("acted"):
            store.add_learning(vid, ts, "content_failed", {"goal": outcome["goal_id"], "titles": d.get("content_titles", []),
                                                           "action": d.get("action"), "decision_id": outcome["decision_id"]})
    else:
        store.add_learning(vid, ts, "inconclusive", {"goal": outcome["goal_id"], "reason": outcome["reason"]})
