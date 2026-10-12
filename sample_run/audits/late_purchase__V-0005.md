# Audit: V-0005

## Evidence received (23 events)
- E0070370 `purchase` happened 2026-10-01T14:09:00Z (device clock), received 2026-10-01T14:12:30Z
- E0070369 `app_open` happened 2026-10-01T14:09:43Z (device clock), received 2026-10-01T14:10:00Z
- S0000017 `app_open` happened 2026-10-01T19:09:32Z (device clock), received 2026-10-01T19:10:01Z
- S0000018 `play_start` happened 2026-10-01T19:10:02Z (device clock), received 2026-10-01T19:10:56Z
- S0000019 `episode_complete` happened 2026-10-01T19:55:02Z (device clock), received 2026-10-01T19:55:40Z
- S0000020 `app_open` happened 2026-10-03T20:09:34Z (device clock), received 2026-10-03T20:10:14Z
- S0000021 `play_start` happened 2026-10-03T20:10:04Z (device clock), received 2026-10-03T20:10:58Z
- S0000022 `app_open` happened 2026-10-05T19:11:38Z (device clock), received 2026-10-05T19:12:37Z
- S0000023 `play_start` happened 2026-10-05T19:12:08Z (device clock), received 2026-10-05T19:12:19Z
- S0000024 `app_open` happened 2026-10-07T22:46:34Z (device clock), received 2026-10-07T22:47:31Z
- S0000025 `app_open` happened 2026-10-08T18:42:49Z (device clock), received 2026-10-08T18:42:56Z
- S0000026 `play_start` happened 2026-10-08T18:43:19Z (device clock), received 2026-10-08T18:44:07Z

Profile snapshot rows: 1 (newest updated 2026-09-29T16:30:00Z: status never_paid, dialect d2)

## Decisions

### D-01318 · 2026-10-01T14:10:00Z · app_open → **PUBLISHED** `IN_APP`
- Goal: G05 first_paid_plan_7d (deadline 2026-10-08T14:10:00Z, new)
- Dialect: used d1 from app_setting; conflicts ['profile:d2']
- Confidence 0.55: 1 dialect source(s) disagree with the app setting; subscription from a stale snapshot
- Reason: viewer is in session and the goal is a plan purchase: show the plan offer
- Checks passed: ['dialect_matches_app', 'eligibility', 'evidence_resolves', 'frequency_cap', 'goal_measurable', 'in_session', 'not_duplicate_action', 'policy_scope', 'quiet_hours', 'template_approved']; failed: []
- Evidence: event:E0070369, profile:V-0005#row4, event:E0000061, goal_rule:G05-e1
- Decided in 9480 ms; calls 2 model / 4 tool

### D-01335 · 2026-10-01T14:12:30Z · state_change → **PUBLISHED** `HOME_PAGE`
- Goal: G03 second_episode_3d (deadline 2026-10-04T14:12:30Z, new)
- Dialect: used d1 from app_setting; conflicts ['profile:d2']
- Content: title:T0952, title:T0325, title:T0396, title:T0838, title:T0769, title:T0175
- Confidence 0.6: 1 dialect source(s) disagree with the app setting
- Reason: home-page row of goal-appropriate titles in the app dialect
- Checks passed: ['content_available', 'content_dialect', 'content_not_quarantined', 'dialect_matches_app', 'eligibility', 'evidence_resolves', 'goal_measurable', 'no_duplicate_variant', 'not_duplicate_action', 'policy_scope', 'row_size']; failed: []
- Evidence: event:E0000061, goal_rule:G03-e1, event:E0070370, event:E0070369, profile:V-0005#row4, catalogue:T0952, catalogue:T0325, catalogue:T0396
- Decided in 4980 ms; calls 1 model / 4 tool

## Outcomes
- G05 (D-01318, treatment): **INCONCLUSIVE**: premise false at decision time (late data): purchase event:E0070370 happened at 2026-10-01T14:09:00Z but arrived at 2026-10-01T14:12:30Z, after decision D-01318
- G03 (D-01335, treatment): **SUCCEEDED**: episode_complete at 2026-10-01T19:55:02Z; attribution goal_met_other_content

## Learned
- 2026-10-01T14:12:30Z inconclusive: {"goal": "G05", "reason": "premise false at decision time (late data): purchase event:E0070370 happened at 2026-10-01T14:09:00Z but arrived at 2026-10-01T14:12:30Z, after decision D-01318"}
- 2026-10-01T14:12:30Z plan_revised: {"closed": "G05", "verdict": "INCONCLUSIVE", "reason": "premise false at decision time (late data): purchase event:E0070370 happened at 2026-10-01T14:09:00Z but arrived at 2026-10-01T14:12:30Z, after decision D-01318"}
- 2026-10-11T18:00:01Z what_worked: {"goal": "G03", "action": "HOME_PAGE", "dialect": "d1", "attribution": "goal_met_other_content", "decision_id": "D-01335"}
- 2026-10-11T18:00:01Z dialect_confirmed: {"dialect": "d1", "by": ["event:S0000019"]}