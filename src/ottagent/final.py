"""Final report and per-viewer audits for the scenarios the brief calls out."""
import json
import os
from collections import Counter

from .reports import explain


def _first(decisions, pred):
    return next((d for d in decisions if pred(d)), None)


def final_report(store, decisions, outcomes, meta, lat, imp, out_dir):
    sc = meta["scenario"]
    adir = os.path.join(out_dir, "audits")
    os.makedirs(adir, exist_ok=True)
    trig = [d for d in decisions if d["trigger"].get("event") == "app_open"]
    statuses = Counter(d["status"] for d in decisions)
    reasons = Counter((d["reason"] or "").split(":")[0] for d in decisions if d["status"] == "NO_ACTION")
    actions = Counter(d["action"] for d in decisions if d["status"] == "PUBLISHED")
    verdicts = Counter(o["verdict"] for o in outcomes)
    corr = [json.loads(l) for l in open(os.path.join(out_dir, "corrections.jsonl"), encoding="utf-8")]
    changed = [o for o in outcomes if o.get("verdict_changed_by_rule_correction")]

    halluc = _first(decisions, lambda d: d["viewer_id"] in sc["llm_hallucinates_eligibility_for"] and d["model"]["outputs_rejected"])
    stale = _first(decisions, lambda d: (d["reason"] or "").startswith("STALE"))
    degraded = _first(decisions, lambda d: (d["reason"] or "").startswith("DEGRADED"))
    shed = _first(decisions, lambda d: any(u["status"] in ("circuit_open", "timeout") for u in d["model"]["used"]) and d["status"] == "PUBLISHED")
    dup = Counter(json.loads(l)["result"] for l in open(os.path.join(out_dir, "trigger_log.jsonl"), encoding="utf-8"))
    worked = _first(sorted(outcomes, key=lambda o: o["decision_id"]),
                    lambda o: o.get("attribution") == "via_served_content" and o["goal_id"] == "G01")
    audits = {"three_dialects": sc["three_dialects_viewer"], "late_purchase": sc["late_purchase_viewer"],
              "model_hallucination": halluc and halluc["viewer_id"], "stale_buffered_open": stale and stale["viewer_id"],
              "rule_correction_changed_verdict": changed and changed[0]["viewer_id"],
              "served_and_succeeded": worked and worked["viewer_id"]}
    for k, v in audits.items():
        if v:
            open(os.path.join(adir, f"{k}__{v}.md"), "w", encoding="utf-8").write(explain(store, v))

    q = lambda r: f"{r['diff_pp']:+.1f} pp [95% CI {r['ci95_pp'][0]:+.1f}, {r['ci95_pp'][1]:+.1f}]"
    md = f"""# Final report: sample replay

Replay of {meta['pack']['triggers']} app-open triggers (17:00-23:30 IST, 1 Oct 2026) over a synthetic pack of
{meta['pack']['viewers']} viewers, {meta['pack']['events']} history events and {meta['pack']['titles']} titles,
then 10 simulated days of viewer behaviour and judging. Model: deterministic mock (no API key needed).

## What the agent did
- Decisions: {len(decisions)} ({len(trig)} from app opens, {len(meta['state_change_decisions'])} re-plans after new data).
- Status: {dict(statuses)}.
- Published actions: {dict(actions)}.
- Reasons for no action: {dict(reasons)}.
- Trigger handling: {dict(dup)}.
- Goals judged: {dict(verdicts)}.

## Timeliness
p50 {lat['decided_in_ms']['p50']} ms, p95 {lat['decided_in_ms']['p95']} ms, max {lat['decided_in_ms']['max']} ms;
{lat['over_60s']} decisions over 60 s, {lat['over_5min']} over 5 min. Max calls in one decision:
{lat['max_model_calls_in_a_decision']} model / {lat['max_tool_calls_in_a_decision']} tool
(budget {lat['budget']['model_calls']} / {lat['budget']['tool_calls']}). Details: `latency_report.json`.

## Impact (details in `impact_report.md`)
ITT, treatment vs holdout: first full episode within 3 days {q(imp['itt_complete_3d'])};
first-goal success {q(imp['itt_first_goal_success'])}. Served-vs-unserved would have reported
{q(imp['naive_served_vs_unserved_complete_3d'])}. The pilot's internal "uplift" re-analysed against its holdout
is {q(imp['pilot']['itt'])} ITT.

## Surprise events: what happened
| Surprise | How the agent noticed | What it did | Where to look |
|---|---|---|---|
| Buffered offline app opens, days old | event effective time vs receipt time | stored for history, **no action** (viewer has left that session) | {stale and stale['decision_id']}, `audits/stale_buffered_open__*.md` |
| Profile says never paid; purchase arrives 2 min after decision | new purchase event re-plans the viewer; its effective time is *before* the decision | G05 closed **INCONCLUSIVE (premise false, late data)**, not counted as a success; new goal chosen | `audits/late_purchase__{sc['late_purchase_viewer']}.md` |
| App setting, profile and campaign name three dialects | per-fact precedence | content in the **app-setting** dialect (what the viewer sees); other two kept as conflicts, confidence lowered | `audits/three_dialects__{sc['three_dialects_viewer']}.md` |
| Goal success condition corrected mid-replay | versioned rule update | only the {corr[0]['affected_active_goals'] if corr else 0} open G01 goals touched (no reprocessing of other viewers); judged under v2 and v1 verdict reported; {len(changed)} verdicts changed | `corrections.jsonl`, `audits/rule_correction_changed_verdict__*.md` |
| Model asserts eligibility with no evidence | independent eligibility check against stored events | claim **rejected** and recorded; goal unchanged | {halluc and halluc['decision_id']}, `audits/model_hallucination__*.md` |
| Catalogue description tells the agent to message every viewer | catalogue scan at load | title {', '.join(meta['quarantined_titles'])} **quarantined**: never shown, never sent to the model. A broadcast proposed by the model is rejected (see tests) | `run_meta.json` |
| Model unavailable for 5 min / store down then slow | timeouts, circuit breaker, budget | model skipped, rules-only ranking; when the store is down, **no action** (cannot verify) | {shed and shed['decision_id']}, {degraded and degraded['decision_id']} |
| Traffic triples for 10 min | queue wait in the latency budget | queue absorbed by workers; model skipped if a trigger waited > {meta['config']['queue_shed_ms'] // 1000} s | `latency_report.json` → windows |

## Disabled goals (data, not guesses)
""" + "\n".join(f"- {g}: {r}" for g, r in meta["measurability"].items() if r) + """

## Walk one viewer
Each file in `audits/` is the output of `python -m ottagent explain <viewer>`: the evidence the agent had, every
decision with its goal, dialect, content, confidence, checks and evidence, then the judged outcome and what was
learned. Add `--at <ISO time>` to see the viewer as the agent saw it at that moment.
"""
    open(os.path.join(out_dir, "final_report.md"), "w", encoding="utf-8").write(md)
    return audits
