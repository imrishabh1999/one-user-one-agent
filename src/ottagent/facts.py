"""Assemble what is known about one viewer, with source, time and freshness for every fact.

Precedence rules (per fact, never "largest/newest source wins" by default):

  subscription  purchase events (append-only, fresh) > profile snapshot (a day stale) > sign_up event.
                A profile 'paid' row is re-derived against sub_expires_at at decision time.
  signup        profile.signup_date > sign_up event; either one is enough evidence of an account.
  dialect       for content shown in the app: the app setting on the triggering event, because that is
                what the viewer will actually see. Profile preference, campaign link and watch history
                are kept as recorded conflicts and lower confidence; they never override the app setting.
  consent       profile snapshot only. Missing or ambiguous consent is treated as NO consent.
  timestamps    device_ts unless the viewer's device clock is consistently off (median offset > 1 h),
                then corrected by that offset; never later than the server receipt time.
Duplicate profile rows: newest updated_at wins; equal timestamps with different values make that
field ambiguous (value None) instead of silently picking one.
"""
from .config import iso

DAY = 86_400
TRIAL_DAYS = 14
PLAN_DAYS = 30


def _fact(value, source, ref, observed_at, now, conflicts=None, note=None):
    return {"value": value, "source": source, "ref": ref,
            "observed_at": iso(observed_at) if observed_at else None,
            "age_s": int(now - observed_at) if observed_at else None,
            "conflicts": conflicts or [], "note": note}


def resolve_profile(rows):
    """Return (profile_dict_or_None, notes, ambiguous_fields)."""
    if not rows:
        return None, ["no profile row (viewer newer than snapshot or missing)"], []
    rows = sorted(rows, key=lambda r: r["updated_at"], reverse=True)
    top = dict(rows[0])
    notes, ambiguous = [], []
    if len(rows) > 1:
        notes.append(f"{len(rows)} profile rows; using newest updated_at {rows[0]['updated_at']}")
        for other in rows[1:]:
            if other["updated_at"] == rows[0]["updated_at"]:
                for k in ("subscription_status", "preferred_dialect", "consent_push", "consent_whatsapp"):
                    if other[k] != top[k] and k not in ambiguous:
                        ambiguous.append(k)
        for k in ambiguous:
            top[k] = None
        if ambiguous:
            notes.append(f"duplicate rows with identical updated_at disagree on {ambiguous}; treated as unknown")
    return top, notes, ambiguous


def assemble(viewer_id, now, trigger_event, events, ev_meta, profile_rows, memory, catalogue, cfg):
    from .config import parse
    facts, refs = {}, []
    prof, prof_notes, prof_ambiguous = resolve_profile(profile_rows)
    prof_ts = parse(prof["updated_at"]) if prof else None
    prof_ref = f"profile:{viewer_id}#row{prof['_row_no']}" if prof else None

    by_type = {}
    for e in events:
        by_type.setdefault(e["type"], []).append(e)
    signups = by_type.get("sign_up", [])
    purchases = by_type.get("purchase", [])
    plays = by_type.get("play_start", [])
    completes = by_type.get("episode_complete", [])
    opens = by_type.get("app_open", [])
    searches = by_type.get("search", [])

    # ---- account / signup
    if prof and prof.get("signup_date"):
        facts["signup"] = _fact(prof["signup_date"], "profile_snapshot", prof_ref, prof_ts, now, note="; ".join(prof_notes) or None)
        signup_ts = parse(prof["signup_date"])
    elif signups:
        s = signups[0]
        facts["signup"] = _fact(iso(s["effective_ts"]), "event", f"event:{s['event_id']}", s["received_ts"], now,
                                note="no profile row; sign_up event used")
        signup_ts = s["effective_ts"]
    else:
        facts["signup"] = _fact(None, "none", None, None, now, note="no profile row and no sign_up event")
        signup_ts = None

    # ---- subscription
    conflicts = []
    prof_status = prof.get("subscription_status") if prof else None
    if purchases:
        last = max(purchases, key=lambda e: e["effective_ts"])
        paid_until = last["effective_ts"] + PLAN_DAYS * DAY
        status = "paid" if paid_until > now else "lapsed"
        if prof_status and prof_status != status:
            conflicts.append(f"profile:{prof_status}@{prof['updated_at']}")
        facts["subscription"] = _fact(status, "purchase_event", f"event:{last['event_id']}", last["received_ts"], now,
                                      conflicts, note=f"paid_until {iso(paid_until)}; purchase events outrank the stale snapshot")
        facts["sub_expires_at"] = _fact(iso(paid_until), "derived:purchase+30d", f"event:{last['event_id']}", last["received_ts"], now)
        ever_paid = True
    elif prof and prof_status:
        status = prof_status
        note = "from profile snapshot"
        if status == "paid" and prof.get("sub_expires_at") and parse(prof["sub_expires_at"]) <= now:
            status, note = "lapsed", "profile said paid but sub_expires_at has passed"
        if status == "trial" and signup_ts and now - signup_ts > TRIAL_DAYS * DAY:
            status, note = "never_paid", "profile said trial but trial window has ended since the snapshot"
        facts["subscription"] = _fact(status, "profile_snapshot", prof_ref, prof_ts, now, note=note)
        if prof.get("sub_expires_at"):
            facts["sub_expires_at"] = _fact(prof["sub_expires_at"], "profile_snapshot", prof_ref, prof_ts, now)
        ever_paid = status in ("paid", "lapsed")
    elif signups:
        s = signups[0]
        status = "trial" if now - s["effective_ts"] <= TRIAL_DAYS * DAY else "never_paid"
        facts["subscription"] = _fact(status, "event", f"event:{s['event_id']}", s["received_ts"], now,
                                      note="no profile; derived from sign_up plan and date")
        ever_paid = False
    else:
        facts["subscription"] = _fact(None, "none", None, None, now, note="ambiguous or missing")
        ever_paid = None
    if facts["subscription"]["value"] in ("trial", "never_paid") and signup_ts and now - signup_ts <= TRIAL_DAYS * DAY:
        facts["subscription"]["value"] = "trial"
        facts["trial_ends_at"] = _fact(iso(signup_ts + TRIAL_DAYS * DAY), "derived:signup+14d",
                                       facts["signup"]["ref"], None, now)

    # ---- dialect
    app_d = trigger_event.get("app_dialect") if trigger_event else None
    app_ref, app_ts = (f"event:{trigger_event['event_id']}", trigger_event["received_ts"]) if trigger_event else (None, None)
    if not app_d:
        recent = [e for e in reversed(events) if e.get("app_dialect") and now - e["received_ts"] <= cfg.app_setting_fresh_s]
        if recent:
            app_d, app_ref, app_ts = recent[0]["app_dialect"], f"event:{recent[0]['event_id']}", recent[0]["received_ts"]
    sources = []
    if app_d:
        sources.append(("app_setting", app_d, app_ref, app_ts))
    if prof and prof.get("preferred_dialect"):
        sources.append(("profile", prof["preferred_dialect"], prof_ref, prof_ts))
    camp = next((s["payload"].get("campaign_dialect") for s in signups if s["payload"].get("campaign_dialect")), None)
    if camp:
        sources.append(("campaign_link", camp, f"event:{signups[0]['event_id']}", signups[0]["received_ts"]))
    hist = {}
    for c in completes:
        d = c["payload"].get("dialect")
        if d:
            hist[d] = hist.get(d, 0) + 1
    if hist:
        top_d = max(hist, key=hist.get)
        sources.append(("watch_history", top_d, f"history:{viewer_id}:{hist}", completes[-1]["received_ts"]))
    if sources:
        used = sources[0]
        dconf = [f"{s[0]}:{s[1]}" for s in sources[1:] if s[1] != used[1]]
        facts["dialect"] = _fact(used[1], used[0], used[2], used[3], now, dconf,
                                 note="app setting is what the viewer sees; others recorded as conflicts" if dconf else None)
    else:
        facts["dialect"] = _fact(None, "none", None, None, now, note="no dialect evidence")

    # ---- consent
    for k in ("consent_push", "consent_whatsapp"):
        if prof and prof.get(k) not in (None, ""):
            facts[k] = _fact(str(prof[k]) == "1", "profile_snapshot", prof_ref, prof_ts, now)
        else:
            facts[k] = _fact(False, "default_no_consent", None, None, now,
                             note="no reliable consent record; treated as no consent")

    # ---- behavioural features (all derived from events, each with refs)
    trig_ts = trigger_event["effective_ts"] if trigger_event else now
    completed_eps = {(c["payload"]["title_id"], c["payload"]["episode"]) for c in completes}
    started_titles = {p["payload"]["title_id"] for p in plays}
    prior_opens = [o for o in opens if o["effective_ts"] < trig_ts - 60]
    last_open = prior_opens[-1] if prior_opens else None
    recent_search = [s for s in searches if 0 <= trig_ts - s["effective_ts"] <= DAY]
    search_wo_play = bool(recent_search) and not any(p["effective_ts"] > recent_search[-1]["effective_ts"] for p in plays)
    series_progress = {}
    for (tid, ep) in completed_eps:
        t = catalogue.get(tid)
        if t and t["format"] == "series":
            series_progress[tid] = max(series_progress.get(tid, 0), ep)
    half_series = [tid for tid, ep in series_progress.items()
                   if ep >= catalogue[tid]["episodes"] / 2 and ep < catalogue[tid]["episodes"]]
    genres = {}
    for p in plays:
        t = catalogue.get(p["payload"]["title_id"])
        if t:
            genres[t["genre"]] = genres.get(t["genre"], 0) + 1
    features = {
        "signed_up": facts["signup"]["value"] is not None,
        "signup_ts": signup_ts,
        "n_events": len(events), "n_plays": len(plays), "n_completions": len(completes),
        "completed_eps": sorted(completed_eps), "started_titles": sorted(started_titles),
        "completion_refs": [f"event:{c['event_id']}" for c in completes[-3:]],
        "play_refs": [f"event:{p['event_id']}" for p in plays[-3:]],
        "last_open_before_trigger": iso(last_open["effective_ts"]) if last_open else None,
        "last_open_ref": f"event:{last_open['event_id']}" if last_open else None,
        "gap_days_since_last_open": round((trig_ts - last_open["effective_ts"]) / DAY, 1) if last_open else None,
        "recent_search_without_play": search_wo_play,
        "search_ref": f"event:{recent_search[-1]['event_id']}" if recent_search else None,
        "half_watched_series": half_series,
        "completion_dialects": hist,
        "genre_affinity": genres,
        "ever_paid": ever_paid,
        "distinct_open_days_14d": len({iso(o["effective_ts"])[:10] for o in opens if trig_ts - o["effective_ts"] <= 14 * DAY}),
    }
    return {"viewer_id": viewer_id, "now": now, "facts": facts, "features": features,
            "event_meta": ev_meta, "profile_notes": prof_notes, "memory": memory}
