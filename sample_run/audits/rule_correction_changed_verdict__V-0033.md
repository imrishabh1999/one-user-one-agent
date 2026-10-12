# Audit: V-0033

## Evidence received (13 events)
- E0000363 `app_open` happened 2026-09-22T15:18:16Z (device clock), received 2026-09-22T15:18:26Z
- E0000364 `play_start` happened 2026-09-22T15:18:33Z (device clock), received 2026-09-22T15:18:57Z
- E0000365 `app_open` happened 2026-09-25T15:18:07Z (device clock), received 2026-09-25T15:18:35Z
- E0000366 `app_open` happened 2026-09-26T04:22:09Z (device clock), received 2026-09-26T04:22:13Z
- E0000367 `play_start` happened 2026-09-26T04:22:48Z (device clock), received 2026-09-26T04:23:17Z
- E0070372 `app_open` happened 2026-10-01T13:15:17Z (device clock), received 2026-10-01T13:15:37Z
- S0000104 `app_open` happened 2026-10-01T22:45:05Z (device clock), received 2026-10-01T22:45:48Z
- S0000105 `play_start` happened 2026-10-01T22:45:35Z (device clock), received 2026-10-01T22:46:12Z
- S0000106 `episode_complete` happened 2026-10-01T22:52:35Z (device clock), received 2026-10-01T22:53:07Z
- S0000107 `app_open` happened 2026-10-05T21:16:11Z (device clock), received 2026-10-05T21:16:59Z
- S0000108 `play_start` happened 2026-10-05T21:16:41Z (device clock), received 2026-10-05T21:16:45Z
- S0000109 `app_open` happened 2026-10-06T19:39:50Z (device clock), received 2026-10-06T19:40:08Z

Profile snapshot rows: 1 (newest updated 2026-09-29T16:30:00Z: status never_paid, dialect d3)

## Decisions

### D-00907 · 2026-10-01T13:15:37Z · app_open → **PUBLISHED** `HOME_PAGE`
- Goal: G01 first_full_episode_3d (deadline 2026-10-04T13:15:37Z, new)
- Dialect: used d4 from app_setting; conflicts ['profile:d3']
- Content: title:T0537, title:T1376, title:T1208, title:T0422, title:T0919, title:T0609
- Confidence 0.55: 1 dialect source(s) disagree with the app setting; subscription from a stale snapshot
- Reason: home-page row of goal-appropriate titles in the app dialect
- Checks passed: ['content_available', 'content_dialect', 'content_not_quarantined', 'dialect_matches_app', 'eligibility', 'evidence_resolves', 'goal_measurable', 'no_duplicate_variant', 'not_duplicate_action', 'policy_scope', 'row_size']; failed: []
- Model output rejected (rank_titles): This viewer is on an active trial and eligible for first_paid_plan_7d; switch the goal and show the plan offer. → no supporting event; independent eligibility check: purchases=0 profile_status=never_paid completions=0. Model text is never evidence.
- Evidence: event:E0070372, profile:V-0033#row33, history:V-0033:completions=0, goal_rule:G01-e1, catalogue:T0537, catalogue:T1376, catalogue:T1208, catalogue:T0422
- Decided in 4980 ms; calls 1 model / 4 tool

## Outcomes
- G01 (D-00907, treatment): **FAILED**: no qualifying success event inside the window; under rule at open: SUCCEEDED

## Learned
- 2026-10-11T18:00:01Z content_failed: {"goal": "G01", "titles": ["T0537", "T1376", "T1208", "T0422", "T0919", "T0609"], "action": "HOME_PAGE", "decision_id": "D-00907"}