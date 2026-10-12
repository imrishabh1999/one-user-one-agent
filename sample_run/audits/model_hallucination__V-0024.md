# Audit: V-0024

## Evidence received (8 events)
- E0000282 `app_open` happened 2026-09-05T12:35:07Z (device clock), received 2026-09-05T12:35:26Z
- E0000283 `app_open` happened 2026-09-17T16:51:07Z (device clock), received 2026-09-17T16:51:37Z
- E0000284 `app_open` happened 2026-09-19T04:27:21Z (device clock), received 2026-09-19T04:27:48Z
- E0000285 `app_open` happened 2026-09-22T12:48:20Z (device clock), received 2026-09-22T12:48:43Z
- E0000286 `page_view` happened 2026-09-22T12:48:50Z (device clock), received 2026-09-22T12:49:10Z
- E0067439 `app_open` happened 2026-10-01T12:09:55Z (device clock), received 2026-10-01T12:10:07Z
- E0070371 `app_open` happened 2026-10-01T13:14:46Z (device clock), received 2026-10-01T13:15:00Z
- S0000087 `app_open` happened 2026-10-04T19:28:23Z (device clock), received 2026-10-04T19:28:58Z

Profile snapshot rows: 1 (newest updated 2026-09-29T18:30:00Z: status never_paid, dialect d5)

## Decisions

### D-00293 · 2026-10-01T12:10:07Z · app_open → **PUBLISHED** `HOME_PAGE`
- Goal: G02 first_play_24h (deadline 2026-10-02T12:10:07Z, new)
- Dialect: used d4 from app_setting; conflicts ['profile:d5']
- Content: title:T1101, title:T1419, title:T0290, title:T0238, title:T0501, title:T0735
- Confidence 0.55: 1 dialect source(s) disagree with the app setting; subscription from a stale snapshot
- Reason: home-page row of goal-appropriate titles in the app dialect
- Checks passed: ['content_available', 'content_dialect', 'content_not_quarantined', 'dialect_matches_app', 'eligibility', 'evidence_resolves', 'goal_measurable', 'no_duplicate_variant', 'not_duplicate_action', 'policy_scope', 'row_size']; failed: []
- Model output rejected (rank_titles): This viewer is on an active trial and eligible for first_paid_plan_7d; switch the goal and show the plan offer. → no supporting event; independent eligibility check: purchases=0 profile_status=never_paid completions=0. Model text is never evidence.
- Evidence: event:E0067439, profile:V-0024#row24, history:V-0024:plays=0, goal_rule:G02-e1, catalogue:T1101, catalogue:T1419, catalogue:T0290, catalogue:T0238
- Decided in 4980 ms; calls 1 model / 4 tool

### D-00902 · 2026-10-01T13:15:00Z · app_open → **PUBLISHED** `HOME_PAGE`
- Goal: G02 first_play_24h (deadline 2026-10-02T12:10:07Z, continuing)
- Dialect: used d4 from app_setting; conflicts ['profile:d5']
- Content: title:T1101, title:T1419, title:T0290, title:T0238, title:T0501, title:T0735
- Confidence 0.55: 1 dialect source(s) disagree with the app setting; subscription from a stale snapshot
- Reason: home-page row of goal-appropriate titles in the app dialect
- Checks passed: ['content_available', 'content_dialect', 'content_not_quarantined', 'dialect_matches_app', 'eligibility', 'evidence_resolves', 'goal_measurable', 'no_duplicate_variant', 'not_duplicate_action', 'policy_scope', 'row_size']; failed: []
- Model output rejected (rank_titles): This viewer is on an active trial and eligible for first_paid_plan_7d; switch the goal and show the plan offer. → no supporting event; independent eligibility check: purchases=0 profile_status=never_paid completions=0. Model text is never evidence.
- Evidence: event:E0070371, profile:V-0024#row24, history:V-0024:plays=0, goal_rule:G02-e1, catalogue:T1101, catalogue:T1419, catalogue:T0290, catalogue:T0238
- Decided in 4980 ms; calls 1 model / 4 tool

## Outcomes
- G02 (D-00293, treatment): **FAILED**: no qualifying success event inside the window

## Learned
- 2026-10-11T18:00:01Z content_failed: {"goal": "G02", "titles": ["T1101", "T1419", "T0290", "T0238", "T0501", "T0735"], "action": "HOME_PAGE", "decision_id": "D-00293"}