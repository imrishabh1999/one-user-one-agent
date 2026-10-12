# Final report: sample replay

Replay of 3213 app-open triggers (17:00-23:30 IST, 1 Oct 2026) over a synthetic pack of
5000 viewers, 68500 history events and 1500 titles,
then 10 simulated days of viewer behaviour and judging. Model: deterministic mock (no API key needed).

## What the agent did
- Decisions: 3137 (3136 from app opens, 1 re-plans after new data).
- Status: {'NO_ACTION': 747, 'PUBLISHED': 2165, 'HOLDOUT_SUPPRESSED': 225}.
- Published actions: {'IN_APP': 754, 'HOME_PAGE': 1339, 'HERO_SLOT': 72}.
- Reasons for no action: {'NO_ELIGIBLE_GOAL': 582, 'VERIFIER_REJECTED_GOAL': 2, 'STALE_TRIGGER': 151, 'DEGRADED': 12}.
- Trigger handling: {'NO_ACTION': 747, 'PUBLISHED': 2164, 'DUPLICATE_TRIGGER_IGNORED': 77, 'HOLDOUT_SUPPRESSED': 225}.
- Goals judged: {'INCONCLUSIVE': 6, 'FAILED': 1649, 'SUCCEEDED': 136}.

## Timeliness
p50 4980 ms, p95 9480 ms, max 16500 ms;
0 decisions over 60 s, 0 over 5 min. Max calls in one decision:
2 model / 6 tool
(budget 8 / 20). Details: `latency_report.json`.

## Impact (details in `impact_report.md`)
ITT, treatment vs holdout: first full episode within 3 days +1.6 pp [95% CI -2.6, +4.4];
first-goal success +2.0 pp [95% CI -2.6, +5.0]. Served-vs-unserved would have reported
-1.6 pp [95% CI -4.4, +1.0]. The pilot's internal "uplift" re-analysed against its holdout
is +3.0 pp [95% CI -0.6, +5.9] ITT.

## Surprise events: what happened
| Surprise | How the agent noticed | What it did | Where to look |
|---|---|---|---|
| Buffered offline app opens, days old | event effective time vs receipt time | stored for history, **no action** (viewer has left that session) | D-00647, `audits/stale_buffered_open__*.md` |
| Profile says never paid; purchase arrives 2 min after decision | new purchase event re-plans the viewer; its effective time is *before* the decision | G05 closed **INCONCLUSIVE (premise false, late data)**, not counted as a success; new goal chosen | `audits/late_purchase__V-0005.md` |
| App setting, profile and campaign name three dialects | per-fact precedence | content in the **app-setting** dialect (what the viewer sees); other two kept as conflicts, confidence lowered | `audits/three_dialects__V-0010.md` |
| Goal success condition corrected mid-replay | versioned rule update | only the 178 open G01 goals touched (no reprocessing of other viewers); judged under v2 and v1 verdict reported; 21 verdicts changed | `corrections.jsonl`, `audits/rule_correction_changed_verdict__*.md` |
| Model asserts eligibility with no evidence | independent eligibility check against stored events | claim **rejected** and recorded; goal unchanged | D-00293, `audits/model_hallucination__*.md` |
| Catalogue description tells the agent to message every viewer | catalogue scan at load | title T0008 **quarantined**: never shown, never sent to the model. A broadcast proposed by the model is rejected (see tests) | `run_meta.json` |
| Model unavailable for 5 min / store down then slow | timeouts, circuit breaker, budget | model skipped, rules-only ranking; when the store is down, **no action** (cannot verify) | D-01013, D-02069 |
| Traffic triples for 10 min | queue wait in the latency budget | queue absorbed by workers; model skipped if a trigger waited > 15 s | `latency_report.json` → windows |

## Disabled goals (data, not guesses)
- G09: success requires content outside the viewer's app dialect, which this agent never shows
- G11: success signal ['watchlist_add'] never appears in the event stream; unmeasurable
- G12: eligibility text 'Active viewers.' is undefined; not guessing

## Walk one viewer
Each file in `audits/` is the output of `python -m ottagent explain <viewer>`: the evidence the agent had, every
decision with its goal, dialect, content, confidence, checks and evidence, then the judged outcome and what was
learned. Add `--at <ISO time>` to see the viewer as the agent saw it at that moment.
