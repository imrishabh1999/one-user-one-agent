# Audit: V-4427

## Evidence received (16 events)
- E0067227 `app_open` happened 2026-10-01T11:38:35Z (device clock), received 2026-10-01T11:38:55Z
- E0069092 `app_open` happened 2026-10-01T15:44:35Z (device clock), received 2026-10-01T15:44:45Z
- S0010973 `app_open` happened 2026-10-02T22:02:02Z (device clock), received 2026-10-02T22:02:24Z
- S0010974 `play_start` happened 2026-10-02T22:02:32Z (device clock), received 2026-10-02T22:02:43Z
- S0010975 `episode_complete` happened 2026-10-02T22:08:32Z (device clock), received 2026-10-02T22:08:50Z
- S0010976 `app_open` happened 2026-10-03T21:28:32Z (device clock), received 2026-10-03T21:28:51Z
- S0010977 `play_start` happened 2026-10-03T21:29:02Z (device clock), received 2026-10-03T21:29:16Z
- S0010978 `app_open` happened 2026-10-04T20:51:34Z (device clock), received 2026-10-04T20:51:51Z
- S0010979 `play_start` happened 2026-10-04T20:52:04Z (device clock), received 2026-10-04T20:52:16Z
- S0010980 `app_open` happened 2026-10-06T19:01:42Z (device clock), received 2026-10-06T19:02:31Z
- S0010981 `play_start` happened 2026-10-06T19:02:12Z (device clock), received 2026-10-06T19:02:33Z
- S0010982 `episode_complete` happened 2026-10-06T19:37:12Z (device clock), received 2026-10-06T19:38:01Z

Profile snapshot rows: 1 (newest updated 2026-09-29T15:30:00Z: status trial, dialect d4)

## Decisions

### D-00079 · 2026-10-01T11:38:55Z · app_open → **PUBLISHED** `HOME_PAGE`
- Goal: G01 first_full_episode_3d (deadline 2026-10-04T11:38:55Z, new)
- Dialect: used d4 from app_setting; conflicts []
- Content: title:T0669, title:T0830, title:T1278, title:T1101, title:T0282, title:T1044
- Confidence 0.65: subscription from a stale snapshot
- Reason: home-page row of goal-appropriate titles in the app dialect
- Checks passed: ['content_available', 'content_dialect', 'content_not_quarantined', 'dialect_matches_app', 'eligibility', 'evidence_resolves', 'goal_measurable', 'no_duplicate_variant', 'not_duplicate_action', 'policy_scope', 'row_size']; failed: []
- Evidence: event:E0067227, profile:V-4427#row4340, history:V-4427:completions=0, goal_rule:G01-e1, catalogue:T0669, catalogue:T0830, catalogue:T1278, catalogue:T1101
- Decided in 4980 ms; calls 1 model / 4 tool

### D-02181 · 2026-10-01T15:44:45Z · app_open → **PUBLISHED** `HOME_PAGE`
- Goal: G01 first_full_episode_3d (deadline 2026-10-04T11:38:55Z, continuing)
- Dialect: used d4 from app_setting; conflicts []
- Content: title:T0669, title:T0830, title:T1278, title:T1101, title:T0282, title:T1044
- Confidence 0.65: subscription from a stale snapshot
- Reason: home-page row of goal-appropriate titles in the app dialect
- Checks passed: ['content_available', 'content_dialect', 'content_not_quarantined', 'dialect_matches_app', 'eligibility', 'evidence_resolves', 'goal_measurable', 'no_duplicate_variant', 'not_duplicate_action', 'policy_scope', 'row_size']; failed: []
- Evidence: event:E0069092, profile:V-4427#row4340, history:V-4427:completions=0, goal_rule:G01-e1, catalogue:T0669, catalogue:T0830, catalogue:T1278, catalogue:T1101
- Decided in 4980 ms; calls 1 model / 4 tool

## Outcomes
- G01 (D-00079, treatment): **SUCCEEDED**: episode_complete at 2026-10-02T22:08:32Z; attribution via_served_content; under rule at open: SUCCEEDED

## Learned
- 2026-10-11T18:00:01Z what_worked: {"goal": "G01", "action": "HOME_PAGE", "dialect": "d4", "attribution": "via_served_content", "decision_id": "D-00079"}
- 2026-10-11T18:00:01Z dialect_confirmed: {"dialect": "d4", "by": ["event:S0010975"]}