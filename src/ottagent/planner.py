"""Choose the intervention for a goal, and the content in the viewer's app dialect.

Proportionality ladder (smallest change that can plausibly move the goal):
  NONE < HERO_SLOT < HOME_PAGE row < IN_APP message < PUSH < WHATSAPP
Messages are used only when a surface change cannot reach the viewer in time (out of session and a
short deadline) or when the goal is a plan purchase and the viewer is in session (IN_APP offer).
"""
from .config import in_quiet_hours, iso, next_allowed_send, parse

DAY = 86_400
SHORT_FORM_MAX_MIN = 45
SURFACE_FOR_GOAL = {
    "G01": "row_short", "G02": "row_short", "G03": "row_short", "G08": "row_short", "G07": "row_short",
    "G09": "row_short", "G04": "hero_series", "G05": "offer", "G06": "offer", "G10": "offer",
}


def candidate_titles(ctx, goal_id, dialect, catalogue, now, deadline, excluded=()):
    x = ctx["features"]
    completed = {tid for tid, _ in x["completed_eps"]}
    started = set(x["started_titles"])
    horizon = min(deadline, now + DAY)
    aff = x["genre_affinity"]
    total = sum(aff.values()) or 1
    seen_groups, out = {}, []
    for t in catalogue.values():
        if t.get("quarantined") or dialect not in t["dialects"] or t["title_id"] in excluded:
            continue
        if parse(t["available_from"]) > now or (t["available_to"] and parse(t["available_to"]) < horizon):
            continue
        if goal_id in ("G05", "G06", "G10") and not t["premium"]:
            continue
        if goal_id in ("G01", "G02", "G03", "G08") and t["episode_minutes"] > SHORT_FORM_MAX_MIN:
            continue
        if goal_id == "G03" and t["title_id"] in completed and t["format"] == "film":
            continue
        resume = 0.4 if (t["title_id"] in started and goal_id in ("G01", "G03")) else 0.0
        score = 0.5 * aff.get(t["genre"], 0) / total + 0.3 * t["popularity"] + resume
        prev = seen_groups.get(t["variant_group"])
        if prev is not None and prev["score"] >= score:
            continue
        rec = {"title_id": t["title_id"], "score": round(score, 4), "genre": t["genre"], "format": t["format"],
               "popularity": t["popularity"], "genre_match": aff.get(t["genre"], 0) / total,
               "description": t["description"], "variant_group": t["variant_group"], "resume": bool(resume)}
        seen_groups[t["variant_group"]] = rec
    out = sorted(seen_groups.values(), key=lambda r: r["score"], reverse=True)
    return out


def pick_template(templates, channel, dialect):
    for t in templates:
        if t["channel"] == channel and t["dialect"] == dialect and t["approved"]:
            return t
    return None


def propose(ctx, goal, deadline, dialect, catalogue, templates, cfg, now, in_session, excluded, messages_today):
    """Returns an ordered list of proposals, largest first; the agent walks it down on verification failure."""
    gid = goal["id"]
    kind = SURFACE_FOR_GOAL.get(gid, "row_short")
    cands = candidate_titles(ctx, gid, dialect, catalogue, now, deadline, excluded)
    proposals = []
    row = [c["title_id"] for c in cands[: cfg.row_size]]

    if kind == "hero_series":
        series = [s for s in ctx["features"]["half_watched_series"] if any(c["title_id"] == s for c in cands)]
        if series:
            proposals.append({"action": "HERO_SLOT", "content": [series[0]], "why": "continue the half-watched series"})
    if kind == "offer" and in_session and messages_today == 0 and not in_quiet_hours(now, cfg):
        tpl = pick_template(templates, "IN_APP", dialect)
        if tpl:
            proposals.append({"action": "IN_APP", "content": [], "template": tpl, "send_at": iso(now),
                              "why": "viewer is in session and the goal is a plan purchase: show the plan offer"})
    if not in_session and deadline - now <= 2 * DAY and row:
        # out of session with a short deadline: a surface change may never be seen in time
        send_at = next_allowed_send(now, cfg)
        for ch, consent in (("PUSH", "consent_push"), ("WHATSAPP", "consent_whatsapp")):
            tpl = pick_template(templates, ch, dialect)
            if ctx["facts"][consent]["value"] and tpl and send_at < deadline:
                proposals.append({"action": ch, "content": row[:1], "template": tpl, "send_at": iso(send_at),
                                  "why": f"viewer out of session, deadline in {(deadline - now) / 3600:.0f} h"})
                break
    if len(row) >= cfg.min_row_titles:
        proposals.append({"action": "HOME_PAGE", "content": row,
                          "why": "home-page row of goal-appropriate titles in the app dialect"})
    if row:
        proposals.append({"action": "HERO_SLOT", "content": row[:1], "why": "too few titles for a row; single hero title"})
    proposals.append({"action": "NONE", "content": [], "why": "no safe, verifiable intervention available"})
    return proposals, cands


def confidence(ctx, goal_eval, used_llm_rank):
    c, why = 0.7, []
    f, x = ctx["facts"], ctx["features"]
    n_conf = len(f["dialect"]["conflicts"])
    if n_conf:
        c -= min(0.2, 0.1 * n_conf)
        why.append(f"{n_conf} dialect source(s) disagree with the app setting")
    if x["n_events"] < 5:
        c -= 0.15
        why.append("thin history (<5 events)")
    if f["subscription"]["source"] == "profile_snapshot" and (f["subscription"]["age_s"] or 0) > DAY:
        c -= 0.05
        why.append("subscription from a stale snapshot")
    if ctx["event_meta"].get("clock_skew_corrected"):
        c -= 0.05
        why.append("device clock skew corrected")
    if goal_eval["assumptions"]:
        c -= 0.1
        why.append("goal relies on an interpretation of an underspecified rule")
    learned = [l for l in ctx["memory"]["learnings"] if l["kind"] == "dialect_confirmed" and l.get("dialect") == f["dialect"]["value"]]
    if learned:
        c += 0.1
        why.append("dialect confirmed by an earlier completion")
    if x["n_completions"] >= 3:
        c += 0.05
        why.append("solid watch history")
    if not why:
        why.append("fresh, consistent evidence")
    return round(max(0.05, min(0.95, c)), 2), "; ".join(why)
