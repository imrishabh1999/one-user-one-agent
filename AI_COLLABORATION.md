# AI collaboration log

## How the work was split

- **Tool:** Claude (Anthropic, Claude app with code execution), one long session.
- **Claude did:** wrote the synthetic data generator, the agent code, tests, reports and first drafts of
  these documents, and ran everything in a sandbox.
- **I did:** set the scope and priorities from the brief, and made the calls on the open choices.
- **Nothing was accepted untested.** Every module ran in the full replay, and behaviour is pinned by 22 tests.



## What the AI got wrong, and how it was caught

Each item was found by running the code or the tests, not by reading.

1. **Verifier crashed on a malformed decision.** A test fed it a broadcast action ("message every viewer")
   with missing fields. It raised `KeyError` instead of rejecting.
   - *Fix:* the verifier now fails closed. Out-of-scope or malformed decisions are rejected with a
     `policy_scope` / `well_formed` failure.
2. **Agent could decide "before" its own trigger arrived.** When the processing time was earlier than the
   trigger's receipt time, the agent did not see the trigger event. It treated the viewer as out of
   session and chose a push message.
   - *Fix:* decision time is clamped to at least the trigger's receipt time.
3. **A test that could not fail.** The corrected-rule test put its real assertions inside an
   `if goal == "G01"` branch. The viewer actually got G02, so the test passed while checking nothing.
   - *Fix:* rewritten so the viewer deterministically gets G01, with no conditional assertions.
4. **Misleading confidence interval.** The first impact code used a bootstrap CI. With 0 purchases in a
   149-viewer holdout it reported a tight interval [+1.9, +3.8] pp.
   - *Fix:* replaced with Newcombe (Wilson-score) intervals, plus a test that the interval stays wide
     when the control has no events.
5. **A surprise that never fired.** The replay showed zero rejected model claims. The mock only lied when
   consulted on a goal tie, and the chosen viewers had no ties.
   - *Fix:* the ranking call can also carry a goal claim; the agent checks it against stored events,
     rejects it, and records it. Covered by a test and an audit file.
6. **Goal G09 conflicted with the dialect rule.** Pursuing it meant showing content outside the viewer's
   app dialect, which the brief forbids.
   - *Fix:* G09 disabled with the reason recorded, rather than quietly breaking the rule.
7. **"Do nothing" could itself fail verification** (the verifier disagreed with the goal), leaving no decision.
   - *Fix:* explicit `VERIFIER_REJECTED_GOAL` outcome; no goal is opened.
8. **In-app offers were sent at night.** The first version applied quiet hours only to push and WhatsApp.
   A check of `actions.jsonl` found 145 in-app plan offers shown after 22:00 IST.
   - *Fix:* quiet hours now apply to every message type, in both the planner and the verifier. After the
     fix the same check finds 0, and a test covers it.

9. **Crash on Windows (found by me, not by the AI).** I ran the project on my own Windows laptop. The
   tests passed, but the replay crashed while writing `impact_report.md`.
   - *Cause:* files were opened without an explicit encoding. Windows defaults to cp1252, which cannot
     write `≥`. The AI's sandbox runs Linux, where UTF-8 is the default, so it never saw the error.
   - *Fix:* every file is now opened with `encoding="utf-8"`.
   - *Lesson:* "it works on the AI's machine" is not "it works": I re-ran it on mine before trusting it.

## Approaches considered and not taken

- **One prompt that picks titles for every viewer.** Rejected: the brief scores this poorly, and it gives
  no evidence trail. The model only reorders a verified candidate set.
- **Letting the model choose goals or confirm eligibility.** Rejected: eligibility comes from rules over
  stored events. Model text is never evidence.
- **Reporting uplift as served vs unserved.** Rejected: the pilot re-analysis shows it inflates the effect
  (+11.5 pp claimed vs +3.0 pp ITT).
- **Reprocessing all viewers after the rule correction.** Rejected: only the 178 open goals using that rule
  are touched.

## How output was checked

- Full replay run end to end; every surprise traced in `sample_run/audits/`.
- Determinism: two runs give byte-identical `decisions.jsonl` and `outcomes.jsonl`.
- Stress run at a quarter of the capacity: 0 decisions over 60 s.
- Pilot re-analysis recovers the effect built into the synthetic pilot (+2.0 pp on served viewers) inside
  its interval.

## My review (fill in)

## My review

- What I ran myself: installed the project on my Windows laptop, ran the 22 tests (all passed)
  and the full replay; opened explorer.html and checked the surprise walk-throughs.
- What I found: the replay crashed on Windows while writing the impact report (file encoding),
  which never happened in the AI's Linux sandbox. I reported it, it was fixed, and I re-ran it
  to confirm the output matched the AI's run exactly.
- What I changed or rejected, and why: <yahan tab likhna jab tum koi decision khud loge>
- One decision I would make differently: <same>
