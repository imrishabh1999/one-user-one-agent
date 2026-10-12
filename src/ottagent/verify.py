"""Independent verification of a proposed decision.

This module deliberately does NOT reuse facts.py, goals.py or the planner's candidate list. It reads
raw rows from the store again and applies its own, simpler and more conservative logic. When it
disagrees with the decision step, the action is blocked and a smaller action is tried.

Model output is never accepted as evidence: a check passes only on stored records.
"""
import json

from .config import in_quiet_hours, local_day, parse

DAY = 86_400
ALLOWED_ACTIONS = {"HOME_PAGE", "HERO_SLOT", "IN_APP", "PUSH", "WHATSAPP", "NONE"}
MESSAGE_ACTIONS = {"IN_APP", "PUSH", "WHATSAPP"}


def _rows(store, sql, args):
    return [dict(r) for r in store.db.execute(sql, args)]


def _newest_profile(store, vid):
    """Conservative: if the newest two rows tie on updated_at and disagree, return None (unknown)."""
    rows = _rows(store, "SELECT data, updated_at FROM profile_rows WHERE viewer_id=? ORDER BY updated_at DESC", (vid,))
    if not rows:
        return None
    a = json.loads(rows[0]["data"])
    if len(rows) > 1 and rows[1]["updated_at"] == rows[0]["updated_at"] and json.loads(rows[1]["data"]) != a:
        return None
    return a


def independent_eligibility(store, vid, goal_id, now):
    """Re-derive eligibility from raw rows. Returns (ok, reason)."""
    cnt = lambda t: _rows(store, "SELECT COUNT(*) c FROM events WHERE viewer_id=? AND type=? AND received_ts<=?",
                          (vid, t, now))[0]["c"]
    prof = _newest_profile(store, vid)
    purchases = cnt("purchase")
    signup_events = cnt("sign_up")
    has_account = prof is not None or signup_events > 0
    completions = cnt("episode_complete")
    plays = cnt("play_start")
    status = (prof or {}).get("subscription_status")
    never_paid = purchases == 0 and (status in ("trial", "never_paid") or (prof is None and signup_events > 0))
    signup_ts = None
    if prof and prof.get("signup_date"):
        signup_ts = parse(prof["signup_date"])
    elif signup_events:
        signup_ts = _rows(store, "SELECT MIN(device_ts) m FROM events WHERE viewer_id=? AND type='sign_up'", (vid,))[0]["m"]
    on_trial = never_paid and signup_ts is not None and now - signup_ts <= 14 * DAY
    if goal_id == "G01":
        return has_account and completions == 0, f"account={has_account} completions={completions}"
    if goal_id == "G02":
        return has_account and plays == 0, f"account={has_account} plays={plays}"
    if goal_id == "G03":
        return completions == 1, f"completions={completions}"
    if goal_id == "G05":
        return never_paid and completions >= 1, f"purchases={purchases} profile_status={status} completions={completions}"
    if goal_id == "G06":
        return on_trial, f"on_trial={on_trial}"
    if goal_id == "G10":
        last = _rows(store, "SELECT MAX(device_ts) m FROM events WHERE viewer_id=? AND type='purchase' AND received_ts<=?",
                     (vid, now))[0]["m"]
        if last:
            exp = last + 30 * DAY
        elif prof and prof.get("sub_expires_at"):
            exp = parse(prof["sub_expires_at"])
        else:
            return False, "no evidence of a paid plan"
        return 0 < exp - now <= 5 * DAY, f"expires_in_days={(exp - now) / DAY:.1f}"
    if goal_id in ("G04", "G07", "G08", "G09"):
        # behavioural goals: the verifier only confirms an account and some activity exists
        n = _rows(store, "SELECT COUNT(*) c FROM events WHERE viewer_id=? AND received_ts<=?", (vid, now))[0]["c"]
        return has_account and n > 0, f"account={has_account} events={n}"
    return False, "goal not verifiable"


def verify(decision, store, cfg, now, measurable, model_suggestions=None):
    """Returns {'passed': [...], 'failed': [{'check','detail'}]}. Fails closed: a malformed or
    out-of-scope decision is rejected, never crashes the verifier and never slips through."""
    vid = decision.get("viewer_id")
    if decision.get("action") not in ALLOWED_ACTIONS or decision.get("target", vid) != vid:
        return {"passed": [], "failed": [{"check": "policy_scope",
                                          "detail": f"action={decision.get('action')} target={decision.get('target')}"}]}
    try:
        return _verify(decision, store, cfg, now, measurable, model_suggestions)
    except (KeyError, TypeError, ValueError) as ex:
        return {"passed": [], "failed": [{"check": "well_formed", "detail": f"malformed decision: {ex!r}"}]}


def _verify(decision, store, cfg, now, measurable, model_suggestions=None):
    passed, failed = [], []

    def check(name, ok, detail=""):
        (passed.append(name) if ok else failed.append({"check": name, "detail": detail}))

    vid = decision["viewer_id"]
    action = decision["action"]
    check("policy_scope", action in ALLOWED_ACTIONS and decision.get("target", vid) == vid,
          f"action={action} target={decision.get('target')}")
    if model_suggestions:
        for s in model_suggestions:
            check("model_output_policy", False, f"rejected model proposal: {s}")

    goal = decision.get("goal")
    if goal:
        gid = goal["id"]
        check("goal_measurable", measurable.get(gid) is None, measurable.get(gid) or "")
        ok, why = independent_eligibility(store, vid, gid, now)
        check("eligibility", ok, f"{gid}: {why}")
    elif action != "NONE":
        check("goal_present", False, "an action without a goal is not allowed")

    if action == "NONE":
        return {"passed": passed, "failed": failed}

    # dialect: content must exist in the dialect on the viewer's app *now*
    latest = _rows(store, "SELECT app_dialect FROM events WHERE viewer_id=? AND received_ts<=? AND app_dialect IS NOT NULL "
                          "ORDER BY received_ts DESC LIMIT 1", (vid, now))
    app_d = latest[0]["app_dialect"] if latest else None
    used = decision["dialect"]["used"]
    check("dialect_matches_app", app_d is not None and used == app_d, f"decision={used} app_setting={app_d}")

    titles = [c.split(":", 1)[1] for c in decision.get("content", [])]
    groups = set()
    for tid in titles:
        r = store.db.execute("SELECT data, quarantined FROM titles WHERE title_id=?", (tid,)).fetchone()
        if not r:
            check("content_exists", False, tid)
            continue
        t = json.loads(r["data"])
        check("content_not_quarantined", not r["quarantined"], tid)
        check("content_dialect", used in t["dialects"], f"{tid} dialects={t['dialects']} used={used}")
        horizon = min(parse(decision["goal"]["deadline"]), now + DAY) if decision.get("goal") else now + DAY
        avail = parse(t["available_from"]) <= now and (t["available_to"] is None or parse(t["available_to"]) >= horizon)
        check("content_available", avail, f"{tid} window {t['available_from']}..{t['available_to']}")
        check("no_duplicate_variant", t["variant_group"] not in groups, f"{tid} {t['variant_group']}")
        groups.add(t["variant_group"])

    if action == "HOME_PAGE":
        check("row_size", len(titles) >= cfg.min_row_titles, f"{len(titles)} titles < {cfg.min_row_titles}")
    if action == "HERO_SLOT":
        check("hero_size", len(titles) == 1, f"{len(titles)} titles")

    if action in MESSAGE_ACTIONS:
        send_at = parse(decision["send_at"])
        prof = _newest_profile(store, vid)
        if action in ("PUSH", "WHATSAPP"):
            field = "consent_push" if action == "PUSH" else "consent_whatsapp"
            check("consent", prof is not None and str(prof.get(field)) == "1", f"{field}={None if prof is None else prof.get(field)}")
            check("send_before_deadline", decision.get("goal") is None or send_at < parse(decision["goal"]["deadline"]),
                  "message would arrive after the goal deadline")
        # quiet hours apply to every message, including in-app ones shown to a viewer who is using the app
        check("quiet_hours", not in_quiet_hours(send_at, cfg), f"send_at={decision['send_at']}")
        if action == "IN_APP":
            check("in_session", decision.get("in_session", False), "viewer not in session")
        n = store.messages_on_local_day(vid, local_day(send_at))
        check("frequency_cap", n < cfg.max_messages_per_local_day, f"{n} message(s) already on {local_day(send_at)}")
        tpl = decision.get("template") or {}
        check("template_approved", tpl.get("approved") is True and tpl.get("channel") == action and tpl.get("dialect") == used,
              f"template={tpl.get('id')}")

    # duplicate action: same channel + same content already published recently
    recent = store.actions_for(vid, since=now - cfg.duplicate_action_window_s)
    dup = any(a["channel"] == action and a.get("content") == decision.get("content") for a in recent)
    check("not_duplicate_action", not dup, "identical action already live for this viewer")

    # every evidence reference must resolve to a stored record
    bad = []
    for ref in decision.get("evidence", []):
        kind, _, key = ref.partition(":")
        if kind == "event" and not store.event(key):
            bad.append(ref)
        if kind == "catalogue" and not store.title(key):
            bad.append(ref)
    check("evidence_resolves", not bad, f"unresolved: {bad}")
    return {"passed": sorted(set(passed)), "failed": failed}
