"""Goal eligibility from the assembled context (the *planner's* view).

The verifier re-derives eligibility separately (verify.py) from raw store rows, so the two can
disagree; disagreement blocks the action.

Catalogue defects and how they are handled:
  G06 'trial near expiry'  -> operationalised as <= 3 days of trial left; recorded as an assumption on
                              every decision that uses it (rule id G06-e1#interp-3d).
  G12 'active viewers'     -> not operationalised; goal disabled until the definition is clarified.
  G11 success 'watchlist_add' -> no such event exists in the stream; goal disabled as unmeasurable.
"""
from .config import parse

DAY = 86_400
G06_NEAR_EXPIRY_DAYS = 3
UNDERSPECIFIED_DISABLED = {
    "G12": "eligibility text 'Active viewers.' is undefined; not guessing",
    # policy conflict, not a data problem: success needs a play in a *different* dialect, but the agent
    # only shows content in the dialect the viewer's app is set to. Pursuing it would mean showing
    # content the viewer may not understand, so it stays off until product decides how to do it safely.
    "G09": "success requires content outside the viewer's app dialect, which this agent never shows",
}


def measurability(goal_rules, observed_event_types):
    """goal_id -> None if usable, else reason it is disabled."""
    out = {}
    for gid, g in goal_rules.items():
        missing = [t for t in g["success"]["event_types"] if t not in observed_event_types]
        if missing:
            out[gid] = f"success signal {missing} never appears in the event stream; unmeasurable"
        elif gid in UNDERSPECIFIED_DISABLED:
            out[gid] = UNDERSPECIFIED_DISABLED[gid]
        else:
            out[gid] = None
    return out


def check_requirement(req, ctx, now):
    """Returns (ok: bool|None, evidence_refs, assumption_or_None). None = cannot tell."""
    f, x = ctx["facts"], ctx["features"]
    sub = f["subscription"]["value"]
    sub_ref = f["subscription"]["ref"]
    if req == "signed_up":
        return x["signed_up"], [f["signup"]["ref"]] if f["signup"]["ref"] else [], None
    if req == "no_completed_episode":
        return x["n_completions"] == 0, [f"history:{ctx['viewer_id']}:completions=0"], None
    if req == "no_play":
        return x["n_plays"] == 0, [f"history:{ctx['viewer_id']}:plays=0"], None
    if req == "exactly_one_completed":
        return x["n_completions"] == 1, x["completion_refs"], None
    if req == "completed_any":
        return x["n_completions"] >= 1, x["completion_refs"], None
    if req == "series_half_watched":
        return bool(x["half_watched_series"]), [f"catalogue:{t}" for t in x["half_watched_series"]], None
    if req == "never_paid":
        if sub is None:
            return None, [], None
        return sub in ("trial", "never_paid"), [sub_ref], None
    if req == "on_trial":
        if sub is None:
            return None, [], None
        return sub == "trial", [sub_ref], None
    if req == "trial_near_expiry":
        te = f.get("trial_ends_at")
        if not te:
            return False, [], None
        left = (parse(te["value"]) - now) / DAY
        return 0 < left <= G06_NEAR_EXPIRY_DAYS, [te["ref"]], \
            f"G06-e1#interp-3d: 'near expiry' interpreted as <= {G06_NEAR_EXPIRY_DAYS} days of trial left (rule underspecified)"
    if req == "paid":
        return sub == "paid", [sub_ref], None
    if req == "sub_expires_within_5d":
        se = f.get("sub_expires_at")
        if not se:
            return False, [], None
        left = (parse(se["value"]) - now) / DAY
        return 0 < left <= 5, [se["ref"]], None
    if req == "returning_after_14d_gap":
        gap = x["gap_days_since_last_open"]
        if gap is None:
            return False, [], None
        return gap >= 14, [x["last_open_ref"]], None
    if req == "recent_search_without_play":
        return x["recent_search_without_play"], [x["search_ref"]] if x["search_ref"] else [], None
    if req == "completed_3_single_dialect":
        return x["n_completions"] >= 3 and len(x["completion_dialects"]) == 1, x["completion_refs"], None
    return None, [], None


def evaluate(ctx, goal_rules, disabled, now):
    """goal_id -> {eligible, reasons, evidence, assumptions}."""
    res = {}
    for gid, g in goal_rules.items():
        if disabled.get(gid):
            res[gid] = {"eligible": False, "reasons": [f"disabled: {disabled[gid]}"], "evidence": [], "assumptions": []}
            continue
        ok, ev, asm, reasons = True, [], [], []
        for req in g["eligibility"]["requires"]:
            r, refs, a = check_requirement(req, ctx, now)
            ev += [x for x in refs if x]
            if a:
                asm.append(a)
            if r is None:
                ok = False
                reasons.append(f"{req}: unknown (insufficient evidence)")
            elif not r:
                ok = False
                reasons.append(f"{req}: false")
        res[gid] = {"eligible": ok, "reasons": reasons, "evidence": ev + [f"goal_rule:{g['eligibility']['rule_id']}"],
                    "assumptions": asm}
    return res


def deadline_for(goal, ctx, now):
    if goal["window_days"]:
        return now + goal["window_days"] * DAY
    te = ctx["facts"].get("trial_ends_at")
    return parse(te["value"]) if te else now + 3 * DAY
