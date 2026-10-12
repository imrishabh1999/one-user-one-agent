# Architecture

## The loop

```
 trigger (app_open)            new data (purchase, sign_up)          rule correction
        │                               │                                  │
        ▼                               ▼                                  ▼
 ┌──────────────┐  idempotency   ┌──────────────┐                 ┌─────────────────┐
 │ handle_trigger│──────────────▶│   _decide    │◀── re-plan ─────│ apply_rule_update│
 └──────────────┘ trigger_id +   └──────┬───────┘                 └─────────────────┘
                  event_id              │   (version the rule; touch only open goals using it)
        ┌───────────────────────────────┼─────────────────────────────────────┐
        │ 1 UNDERSTAND  facts.assemble: every fact = value + source + ref + age + conflicts
        │ 2 GOAL        keep the active goal / close it (achieved, premise false, superseded) / choose
        │ 3 PLAN        proportionality ladder, content only in the app-setting dialect
        │ 4 VERIFY      verify.verify: own SQL on raw rows; walk down to a smaller action on failure
        │ 5 ACT         PUBLISHED, or HOLDOUT_SUPPRESSED (shadow), or NO_ACTION with a reason
        └───────────────────────────────┬─────────────────────────────────────┘
                                        ▼
                     6 JUDGE (deadline + grace)  ──▶  7 LEARN (viewer state)  ──▶  IMPACT (ITT vs holdout)
```

## Ownership

One logical agent per viewer. All of a viewer's state lives under their `viewer_id` in one store, every path
that can change it goes through `Agent._decide`, and SQLite enforces **at most one ACTIVE goal per viewer**
(a partial unique index), so two components cannot pursue different goals for one viewer. A goal belongs to
the decision that opened it (`goal_instance_id = GI-<decision_id>`); later decisions either continue it or
close it with a recorded reason before opening another.

In production the same rule becomes a per-viewer lock (or partitioning the trigger stream by `viewer_id`), so
one viewer's triggers are processed in order by one worker while different viewers run in parallel.

## Planning

The goal is chosen and revised **when the viewer's situation changes**, never on a timer:

- an app open re-checks the active goal: if its success signal has already been observed it is closed as
  SUCCEEDED early; if the viewer is no longer eligible it is closed and a new goal is chosen;
- new data outside a session (a purchase, a sign-up) triggers a re-plan for that viewer only;
- if the new data shows the goal's **premise was false when we decided** (the purchase happened before the
  decision but arrived after it), the goal is closed INCONCLUSIVE, not counted as a success, and learned from.

Goal choice is rule-based (eligibility + catalogue priority). The model is consulted only to break a near-tie
between eligible goals; its answer must be in the eligible set.

Intervention choice follows a **proportionality ladder**: NONE < HERO_SLOT < HOME_PAGE row < IN_APP < PUSH <
WHATSAPP. Surfaces are preferred; an in-app plan offer is used only for plan goals while the viewer is in
session; push/WhatsApp only when the viewer is out of session *and* the deadline is too close for a
surface change to be seen. Every proposal list ends in NONE.

## Evidence, sources and memory

`facts.py` documents per-fact precedence at the top of the file. The short version:

| Fact | Precedence | Why |
|---|---|---|
| Subscription | purchase events > profile snapshot > sign_up | events are fresh and append-only; the snapshot is a day stale |
| Dialect for content | app setting on the trigger event | it is what the viewer will actually see; profile, campaign and watch history are kept as *conflicts* and lower confidence |
| Consent | profile only; missing or ambiguous = **no consent** | the cost of a wrong "yes" is a policy breach |
| Event time | device time, corrected when the device clock is consistently off; never after receipt | single late events must not be mistaken for a wrong clock (median of offsets) |
| Duplicate profile rows | newest `updated_at`; a tie with different values makes that field unknown | never pick silently |

Nothing larger, newer or more convenient wins by default; each rule is a choice with a reason.

**Memory** (`store.py`) is SQLite with two kinds of tables. *Evidence* (events, profile rows, catalogue,
versioned goal rules) is append-only and keeps its original fields. *Agent records* (goals, decisions,
actions, outcomes, learnings) refer to evidence by id (`event:E…`, `profile:V…#row`, `catalogue:T…`,
`goal_rule:G…`). The agent never reads its own records back as evidence about the viewer. Learnings feed
back into planning: titles from a failed decision are excluded next time; a completion in a dialect raises
confidence for that dialect.

**Audit at any moment**: `python -m ottagent explain <viewer> --at <ISO>` filters every table by time and
shows what the agent had received, what it decided and why, and what it had judged and learned by then.

## Verification

`verify.py` shares **no code** with `facts.py`, `goals.py` or `planner.py`. It re-reads raw rows with its own
simpler, more conservative SQL (for example, any purchase event at all means "has paid"; a tied duplicate
profile row means "unknown"). Checks: policy scope, goal measurable, eligibility, dialect matches the app
*now*, content exists/available/not quarantined/in that dialect, no duplicate language variant, row size,
consent, quiet hours (22:00–08:00 IST), one message per local day, approved template in the right dialect
and channel, send before the deadline, not a duplicate of a live action, every evidence reference resolves.

If a check fails, the agent walks down the ladder to a smaller action and verifies again; if even NONE fails
(the verifier disagrees with the goal itself), no goal is opened. The verifier **fails closed**: a
malformed or out-of-scope decision is rejected, not crashed on.

## Real time and latency

- **Budget per decision**: max 8 model calls and 20 tool calls (`Budget` raises before exceeding them);
  observed max in the sample run is 2 model / 6 tool calls.
- **Latency**: `decided_in_ms` = queue wait + simulated cost of every call, measured from when the trigger
  reached us. Sample run: p50 5.0 s, p95 9.5 s, max 16.5 s; 0 decisions over 60 s.
- **Load shedding**: if a trigger has already waited more than 15 s in the queue, the model is skipped and the
  rules rank content. Stress run with a quarter of the capacity (`--workers 1`): p95 19.7 s, max 48.4 s,
  still 0 decisions over 60 s; the model was skipped 108 times, 61 of them at the 3× evening peak.
- **Idempotency**: duplicate `trigger_id` → returns the original decision; same `event_id` under a new
  trigger → ignored; identical live action → `ALREADY_IN_PLACE`.
- **Stale triggers**: an app open that reached us more than 30 minutes after it happened (buffered offline)
  is stored as history but gets no action: the viewer has left that session.

## Failure recovery

| Failure | Behaviour |
|---|---|
| Model slow/down | 8 s timeout per call; 3 consecutive failures open a circuit breaker for 120 s (half-open after); rules continue alone |
| Store down | the decision cannot assemble or verify evidence → `NO_ACTION (DEGRADED)`. We never act on what we cannot verify |
| Store slow | calls cost more; if a call exceeds the 3 s store timeout it fails as above |
| Budget exhausted | `BudgetExceeded` → degrade to no action |
| Decision > 5 min | `EXPIRED`, not published |

## Trust boundaries

1. **Viewer data and catalogue text are data, never instructions.** Titles whose description reads like an
   instruction are quarantined at load, never shown and never sent to the model.
2. **Model output is advice, never evidence or approval.** It can only reorder titles inside a verified
   candidate set or pick among already-eligible goals. Claims of eligibility, titles outside the set, and
   proposed actions outside the schema (e.g. "message every viewer") are rejected and recorded in
   `decision.model.outputs_rejected`.
3. **Only the verifier approves.** Its approval rests on stored records.
4. **Privacy**: the hosted provider gets only pseudonymous, minimal features; the default mock sends nothing.

## Measurement

Arm assignment is a salted hash of `viewer_id` (10% holdout), fixed before the replay. Holdout viewers get
the full decision, goal and judging, but nothing is published (`HOLDOUT_SUPPRESSED`), so both arms have
comparable shadow goals. Impact is **intent-to-treat** over viewers who opened the app (that does not
depend on arm), with Newcombe 95% CIs. `impact_report.md` also shows why served-vs-unserved and the pilot's
"served vs everyone else" mislead, and recovers the pilot's built-in true effect from its holdout.

Judging uses attributable signals only: this viewer, effective time inside the goal window, received
before deadline + 6 h grace. Later arrivals are listed, not counted. A corrected rule judges open goals
under the new version and also reports the old verdict, flagging changes (21 in the sample run).

## Questions from the brief

**Is what I know current enough to act on?** Each fact carries its age; the app setting comes from the
trigger event itself (seconds old); subscription prefers events over the snapshot; a trigger older than 30
min is not acted on; consent must be present and unambiguous.

**When should the agent do nothing?** When no goal is eligible (often viewers already doing well, e.g. paid
regular watchers), the trigger is stale, evidence cannot be verified, the same action is already live, or
every proposal fails a check. We know it was right by comparing those viewers' outcomes in treatment vs
holdout over time: if doing nothing were costing us, the holdout would not differ.

**1,000 viewers in one minute?** Queue with N workers; load shedding drops the model first; the rules path
costs ~0.5 s. Partition by `viewer_id` so one viewer stays ordered and the rest scale horizontally.

**10 million viewers, 40 dialects?** The store becomes a partitioned key-value store for viewer state plus an
event log (e.g. Kafka) keyed by viewer; precomputed candidate sets per (dialect, goal) refreshed when the
catalogue changes, instead of scanning titles per decision; templates and dialect coverage as data;
holdout per dialect so small dialects are measured too.

**What should never be automated?** Pricing and refunds, anything touching consent records, sending outside
approved templates, acting on a viewer's sensitive inferred attributes, and changing goal definitions or
success rules: a human corrects those (as in the mid-replay correction); the agent only applies versions.
