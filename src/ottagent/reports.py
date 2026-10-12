"""Write the run artefacts: latency report, impact report, final report, per-viewer state and audits."""
import json
import os
from collections import Counter
from datetime import datetime

from .config import IST, iso, parse
from .impact import analyse


def _pct(xs, p):
    xs = sorted(xs)
    return xs[int(p * (len(xs) - 1))] if xs else None


def _window(name, start_local, end_local):
    f = lambda h, m: datetime(2026, 10, 1, h, m, tzinfo=IST).timestamp()
    return name, f(*start_local), f(*end_local)


WINDOWS = [_window("evening_peak_3x_traffic (20:00-20:10 IST)", (20, 0), (20, 10)),
           _window("model_outage (19:00-19:07 IST)", (19, 0), (19, 7)),
           _window("store_outage_then_slow (21:00-21:05 IST)", (21, 0), (21, 5)),
           _window("buffered_offline_burst (18:30-18:31 IST)", (18, 30), (18, 31))]


def all_decisions(store):
    return [json.loads(r["data"]) for r in store.db.execute("SELECT data FROM decisions ORDER BY created_at, decision_id")]


def latency_report(store, decisions, out_dir, agent, cfg):
    trig = [d for d in decisions if d["trigger"].get("event") == "app_open"]
    lat = [d["decided_in_ms"] for d in trig]
    rep = {"decisions": len(trig),
           "decided_in_ms": {"p50": _pct(lat, .5), "p95": _pct(lat, .95), "p99": _pct(lat, .99), "max": max(lat)},
           "queue_wait_ms": {"p50": _pct([d["budget"]["queue_wait_ms"] for d in trig], .5),
                             "max": max(d["budget"]["queue_wait_ms"] for d in trig)},
           "over_60s": sum(x > cfg.latency_target_ms for x in lat), "over_5min": sum(x > cfg.latency_fail_ms for x in lat),
           "max_model_calls_in_a_decision": max(d["budget"]["model_calls"] for d in decisions),
           "max_tool_calls_in_a_decision": max(d["budget"]["tool_calls"] for d in decisions),
           "budget": {"model_calls": cfg.max_model_calls, "tool_calls": cfg.max_tool_calls},
           "workers": cfg.workers, "llm_client": agent.llm.stats,
           "model_skipped_for_load_shedding": sum(1 for d in decisions for u in d["model"]["used"]
                                                  if u["status"] == "skipped_load_shedding"),
           "windows": {}}
    log = [json.loads(l) for l in open(os.path.join(out_dir, "trigger_log.jsonl"), encoding="utf-8")]
    rep["trigger_results"] = dict(Counter(r["result"] for r in log))
    for name, s, e in WINDOWS:
        ds = [d for d in trig if s <= parse(d["trigger"]["received_at"]) < e]
        if not ds:
            continue
        rep["windows"][name] = {
            "decisions": len(ds), "p50_ms": _pct([d["decided_in_ms"] for d in ds], .5),
            "max_ms": max(d["decided_in_ms"] for d in ds),
            "statuses": dict(Counter(d["status"] for d in ds)),
            "model_status": dict(Counter(u["status"] for d in ds for u in d["model"]["used"])),
            "degraded": sum(1 for d in ds if (d["reason"] or "").startswith("DEGRADED")),
            "stale": sum(1 for d in ds if (d["reason"] or "").startswith("STALE"))}
    json.dump(rep, open(os.path.join(out_dir, "latency_report.json"), "w", encoding="utf-8"), indent=1)
    return rep


def write_viewer_state(store, out_dir, viewer_ids):
    vdir = os.path.join(out_dir, "viewer_state")
    os.makedirs(vdir, exist_ok=True)
    for vid in viewer_ids:
        ds = store.decisions_for(vid)
        state = {"viewer_id": vid, "arm": ds[-1]["arm"] if ds else None,
                 "facts_at_last_decision": ds[-1]["facts"] if ds else {},
                 "active_goal": (store.active_goal(vid) or {}).get("goal_instance_id"),
                 "goals": [{k: g[k] for k in ("goal_instance_id", "goal_id", "status", "verdict", "decision_id")} |
                           {"opened_at": iso(g["opened_at"]), "deadline": iso(g["deadline"]), "notes": g["data"].get("notes", [])}
                           for g in store.goals_for(vid)],
                 "decisions": [{k: d.get(k) for k in ("decision_id", "status", "action", "content", "confidence", "reason")} |
                               {"at": d["trigger"]["received_at"], "trigger": d["trigger"].get("event"),
                                "goal": (d.get("goal") or {}).get("id")} for d in ds],
                 "actions": store.actions_for(vid), "outcomes": store.outcomes_for(vid),
                 "learnings": [dict(l, ts=iso(l["ts"])) for l in store.learnings_for(vid)]}
        json.dump(state, open(os.path.join(vdir, f"{vid}.json"), "w", encoding="utf-8"), indent=1, default=str)


def explain(store, vid, at=None):
    """What the agent knew, decided and observed for one viewer, as of `at` (ISO) or now."""
    t = parse(at) if at else float("inf")
    ev_rows = store.db.execute("SELECT event_id, type, device_ts, received_ts FROM events WHERE viewer_id=? AND received_ts<=? "
                               "ORDER BY device_ts", (vid, t)).fetchall()
    lines = [f"# Audit: {vid}" + (f" as of {at}" if at else ""), ""]
    lines.append(f"## Evidence received ({len(ev_rows)} events)")
    for e in ev_rows[-12:]:
        lines.append(f"- {e['event_id']} `{e['type']}` happened {iso(e['device_ts'])} (device clock), "
                     f"received {iso(e['received_ts'])}")
    prof = store.profile_rows(vid)
    lines.append(f"\nProfile snapshot rows: {len(prof)}" + (f" (newest updated {prof[0]['updated_at']}: status "
                                                             f"{prof[0]['subscription_status']}, dialect {prof[0]['preferred_dialect']})" if prof else ""))
    lines.append("\n## Decisions")
    for d in store.decisions_for(vid, None if not at else t):
        g = d.get("goal") or {}
        lines.append(f"\n### {d['decision_id']} · {d['trigger']['received_at']} · {d['trigger'].get('event')} → **{d['status']}** "
                     f"`{d['action']}`")
        lines.append(f"- Goal: {g.get('id')} {g.get('name', '')} (deadline {g.get('deadline')}, "
                     f"{'continuing' if g.get('continuing') else 'new'})" if g else "- Goal: none")
        lines.append(f"- Dialect: used {d['dialect']['used']} from {d['dialect']['source']}; conflicts {d['dialect']['conflicts']}")
        if d["content"]:
            lines.append(f"- Content: {', '.join(d['content'])}")
        lines.append(f"- Confidence {d['confidence']}: {d['confidence_reason']}")
        lines.append(f"- Reason: {d['reason']}")
        lines.append(f"- Checks passed: {d['checks']['passed']}; failed: {d['checks']['failed']}")
        for r in d["rejected_proposals"]:
            lines.append(f"- Rejected proposal {r['action']}: {[f['check'] for f in r['failed']]}")
        for m in d["model"]["outputs_rejected"]:
            lines.append(f"- Model output rejected ({m['task']}): {m.get('claim') or m['proposed']} → {m['why_rejected']}")
        lines.append(f"- Evidence: {', '.join(d['evidence'][:8])}")
        lines.append(f"- Decided in {d['decided_in_ms']} ms; calls {d['budget']['model_calls']} model / {d['budget']['tool_calls']} tool")
    lines.append("\n## Outcomes")
    for o in store.outcomes_for(vid):
        if at and o["judged_at_ts"] > t:
            continue
        extra = f"; under rule at open: {o['verdict_under_rule_at_open']}" if "verdict_under_rule_at_open" in o else ""
        lines.append(f"- {o['goal_id']} ({o['decision_id']}, {o['arm']}): **{o['verdict']}**: {o['reason']}"
                     f"{'; attribution ' + o['attribution'] if o.get('attribution') else ''}{extra}")
    lines.append("\n## Learned")
    for l in store.learnings_for(vid, None if not at else t):
        lines.append(f"- {iso(l['ts'])} {l['kind']}: " + json.dumps({k: v for k, v in l.items() if k not in ('kind', 'ts')}))
    return "\n".join(lines)


def _fmt(r):
    return (f"{100 * r['treat_rate']:.1f}% vs {100 * r['control_rate']:.1f}% (n={r['n_treat']} / {r['n_control']}); "
            f"difference **{r['diff_pp']:+.1f} pp**, 95% CI [{r['ci95_pp'][0]:+.1f}, {r['ci95_pp'][1]:+.1f}], p={r['p_value']}")


def impact_report(store, decisions, outcomes, out_dir, pack_dir):
    a = analyse(store, decisions, outcomes, pack_dir)
    p = a["pilot"]
    md = f"""# Impact report

## How impact is measured
Viewers are assigned to **treatment** or **holdout** by a salted hash of their viewer id before the replay
({100 - 10}/10 split). The population is every viewer who opened the app (fresh, in-session) during the replay;
opening the app does not depend on the arm, so the two groups are comparable. For holdout viewers the agent
makes the full decision (goal, content, checks) but does not publish it, so both arms get the same goals
and the same judging.

The headline is **intent-to-treat (ITT)**: all treatment viewers against all holdout viewers, *including*
treatment viewers the agent chose not to act on. That is the effect of switching the agent on.

**Balance check (pre-replay events per viewer):** treatment {a['balance_pre_events']['treatment']}, holdout
{a['balance_pre_events']['holdout']}: the arms look alike, as randomization should make them. Served viewers
{a['balance_pre_events']['served']} vs unserved {a['balance_pre_events']['unserved']}: these groups differ *before*
the agent did anything, which is why comparing them misleads.

## Results (replay, judged {len(outcomes)} goals)
Population {a['population']} viewers: {a['treatment']} treatment, {a['holdout']} holdout.
The agent acted on {100 * a['served_share_in_treatment']:.0f}% of treatment viewers.

| Metric (ITT, treatment vs holdout) | Result |
|---|---|
| First full episode (watch ≥ 90%) within 3 days | {_fmt(a['itt_complete_3d'])} |
| First goal judged SUCCEEDED (shadow goals for holdout) | {_fmt(a['itt_first_goal_success'])} |
| Purchase within 7 days, viewers never paid at start | {_fmt(a['itt_purchase_7d_never_paid'])} |

First goals left INCONCLUSIVE (not counted either way): {a['first_goal_inconclusive']}.

Per goal (first goal per viewer, successes / judged):
""" + "\n".join(f"- {g}: treatment {v.get('treatment', [0, 0])[0]}/{v.get('treatment', [0, 0])[1]}, "
                f"holdout {v.get('holdout', [0, 0])[0]}/{v.get('holdout', [0, 0])[1]}"
                for g, v in a["first_goal_success_by_goal"].items()) + f"""

The holdout is small (about 10%), so confidence intervals are wide; per-goal splits are descriptive only.

## Why simpler comparisons mislead
**Served vs unserved in this replay:** {_fmt(a['naive_served_vs_unserved_complete_3d'])}.
"Unserved" mixes the holdout with viewers the agent *chose* to skip (no eligible goal, stale trigger,
already-paid). Those choices depend on the viewer, so the groups differed before any action.

**The earlier pilot.** The internal summary says:
> {p['claimed'].splitlines()[-1]}

That compares *served* viewers with *everyone else*. Only viewers who open the app can be served, and app
openers convert more anyway. Re-analysed against the pilot's own randomized holdout:

| Comparison | Result |
|---|---|
| Internal report: served vs everyone else | {_fmt(p['naive_served_vs_rest'])} |
| Openers only, treatment vs holdout | {_fmt(p['openers_only_treat_vs_holdout'])} |
| **ITT: treatment arm vs holdout arm** | {_fmt(p['itt'])} |

Only {100 * p['served_share_in_treatment']:.0f}% of the treatment arm was served, so the implied effect on
those served is about ITT / share = **{p['effect_on_served_cace_pp']:+.1f} pp** (95% CI roughly
[{p['effect_on_served_cace_ci_pp'][0]:+.1f}, {p['effect_on_served_cace_ci_pp'][1]:+.1f}]), nowhere near the claimed uplift.
Because we generated this pilot, we can check: the true effect built into it is **+2.0 pp** on served viewers,
inside that interval. The internal headline mostly measures *who opens the app*, not what the agent did.

In this replay the naive comparison happens to point the *other* way: viewers the agent skipped are heavier
watchers (often already paid, so no goal applies). Selection bias has no fixed sign, which is exactly why
only the randomized comparison is reported as impact.

## Honest caveats
- The outcome simulator and its effect sizes were written by us (see `simulate.py`). The replay shows the
  measurement code recovers an effect without bias; it says nothing about real viewers.
- One evening of triggers and a 10% holdout give limited power. In production, pre-register the primary
  metric and run until the CI excludes the minimum effect worth shipping.
- Goals are judged per viewer, but the business metric (completion, paid conversion) is what the ITT
  rows use; goal success alone could be gamed by choosing easy goals.
"""
    open(os.path.join(out_dir, "impact_report.md"), "w", encoding="utf-8").write(md)
    return a
