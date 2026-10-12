# One User, One Agent

A per-viewer lifecycle agent for a regional-dialect OTT platform. For every viewer it picks one
measurable goal (or none), decides what to change (a home-page row, a hero title, one message, or
nothing) from evidence it can cite, checks that decision independently, publishes within the time
budget, and later judges from real signals whether it worked, measured against a randomized holdout.

No data pack came with the brief, so the repo **generates its own synthetic pack** containing every defect
the brief describes (late, duplicate and clock-skewed events; a stale profile with duplicate rows; dialect
conflicts; language-variant titles; an injected catalogue description; underspecified and unmeasurable
goals; a misleading pilot report) plus a replay script with all eight surprise events.

## Run it

Python 3.10+ only; the agent uses the standard library. `pytest` is needed for tests.

```bash
python -m pip install -e .            # or: export PYTHONPATH=src

python -m ottagent replay             # one command: generates the pack if missing, replays, judges, reports
python -m pytest -q                   # 22 behaviour tests
python -m ottagent explain V-0005     # audit one viewer: what the agent knew, decided and observed
python -m ottagent explain V-0005 --at 2026-10-01T14:11:00Z   # ...as of a past moment
python -m ottagent replay --workers 1 --out stress_run          # same replay with a quarter of the capacity
```

The replay takes about a minute and is deterministic (seeded data, mock model, simulated clock), so an
evaluator gets the same numbers as `sample_run/`.

**Model.** The default is a deterministic mock (`deps.MockLLM`), so no API key is needed. It is deliberately
untrustworthy: it asserts eligibility it has no evidence for, and it obeys instructions hidden in text it is
given. `--llm anthropic` uses a hosted model through the same interface (reads `ANTHROPIC_API_KEY`; sends
only pseudonymous, minimal features). The pack is personal data by assumption, so it is never sent anywhere by
default.

## What is where

```
src/ottagent/
  datagen.py      synthetic pack + replay script (all defects and surprises, seeded)
  catalogues.py   12 goals, interventions, message templates
  store.py        durable state in SQLite: raw evidence + per-viewer goals, decisions, actions, outcomes, learnings
  facts.py        assemble the viewer: every fact with source, time, freshness, conflicts (precedence rules)
  goals.py        eligibility rules (planner's view); disabled/underspecified goals
  planner.py      intervention + content in the viewer's app dialect; proportionality ladder; confidence
  verify.py       independent checks from raw rows; fails closed
  deps.py         budgeted tool client, model client with timeout + circuit breaker, mock & hosted providers
  agent.py        the loop: trigger -> understand -> goal -> plan -> verify -> act; re-plan on new data; rule updates
  judge.py        close the loop: SUCCEEDED / FAILED / INCONCLUSIVE from attributable signals; learning
  replay.py       timed replay with a worker pool and fault injection
  simulate.py     what viewers do in the 10 days after (hidden propensities; holdout untreated)
  impact.py       ITT against the holdout, Newcombe CIs, pilot re-analysis
  reports.py, final.py   latency / impact / final reports, viewer state, audits
tests/            22 tests (late/duplicate triggers, conflicting sources, tool failure, corrected rule, and more)
sample_run/       output of `python -m ottagent replay` (see below)
```

**Start here:** open `sample_run/explorer.html` in a browser. It is one self-contained page (no server) where
you can pick any viewer and walk from app open to judged outcome: goal, dialect and conflicts, content,
confidence, every check, model claims that were rejected, evidence ids, cost, verdict and what was learned. The
six surprise walk-throughs are pinned on the left.

`sample_run/` also has: `decisions.jsonl` (every decision, including no-action and holdout ones), `actions.jsonl`
(what was published), `outcomes.jsonl` (judged goals), `trigger_log.jsonl` (including duplicates ignored),
`corrections.jsonl` (rule correction and what it touched), `viewer_state/<viewer>.json` (durable per-viewer
state), `latency_report.json`, `impact_report.md`, `final_report.md`, and `audits/` (one walk-through file per
surprise). `state.sqlite` is not committed; the replay command recreates it identically.

## Brief → where it is answered

| Brief asks for | Where |
|---|---|
| Understand the viewer with source/time/freshness, explicit conflict resolution | `facts.py` (precedence rules at the top), `decision.facts` |
| One measurable goal with deadline and success signal, or why none | `goals.py`, `decision.goal.judged_by`, `NO_ELIGIBLE_GOAL` reasons |
| Decide the intervention, including doing nothing, in the dialect the viewer sees | `planner.py`, `decision.dialect` |
| Act within budget; degrade safely | `deps.py`, `agent.py`, `latency_report.json` |
| Verify independently of the decision step | `verify.py` (own SQL, no shared code with planner) |
| Close the loop from attributable signals, record what was learned | `judge.py`, `outcomes.jsonl`, `viewer_state/*.json` |
| Prove impact vs randomized holdout; explain why simpler comparisons mislead | `impact.py`, `impact_report.md` |
| Auditability at any moment | `python -m ottagent explain <viewer> --at <time>` |

Design notes: [ARCHITECTURE.md](ARCHITECTURE.md). Gaps left on purpose: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).
How AI tools were used and checked: [AI_COLLABORATION.md](AI_COLLABORATION.md).
