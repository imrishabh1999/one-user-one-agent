# Audit: V-0010

## Evidence received (15 events)
- E0070368 `app_open` happened 2026-10-01T12:34:44Z (device clock), received 2026-10-01T12:35:00Z
- E0069790 `app_open` happened 2026-10-01T17:25:41Z (device clock), received 2026-10-01T17:25:45Z
- S0000054 `app_open` happened 2026-10-02T19:15:41Z (device clock), received 2026-10-02T19:16:10Z
- S0000055 `play_start` happened 2026-10-02T19:16:11Z (device clock), received 2026-10-02T19:16:36Z
- S0000056 `app_open` happened 2026-10-04T22:16:35Z (device clock), received 2026-10-04T22:17:15Z
- S0000057 `play_start` happened 2026-10-04T22:17:05Z (device clock), received 2026-10-04T22:17:23Z
- S0000058 `app_open` happened 2026-10-05T21:41:21Z (device clock), received 2026-10-05T21:41:58Z
- S0000059 `play_start` happened 2026-10-05T21:41:51Z (device clock), received 2026-10-05T21:41:53Z
- S0000060 `app_open` happened 2026-10-07T21:57:43Z (device clock), received 2026-10-07T21:58:01Z
- S0000061 `play_start` happened 2026-10-07T21:58:13Z (device clock), received 2026-10-07T21:58:54Z
- S0000062 `episode_complete` happened 2026-10-07T22:28:13Z (device clock), received 2026-10-07T22:28:54Z
- S0000063 `app_open` happened 2026-10-10T20:38:19Z (device clock), received 2026-10-10T20:38:31Z

Profile snapshot rows: 1 (newest updated 2026-09-29T18:30:00Z: status trial, dialect d1)

## Decisions

### D-00470 · 2026-10-01T12:35:00Z · app_open → **PUBLISHED** `HOME_PAGE`
- Goal: G01 first_full_episode_3d (deadline 2026-10-04T12:35:00Z, new)
- Dialect: used d3 from app_setting; conflicts ['profile:d1', 'campaign_link:d5']
- Content: title:T1395, title:T0758, title:T0385, title:T0012, title:T0533, title:T1219
- Confidence 0.3: 2 dialect source(s) disagree with the app setting; thin history (<5 events); subscription from a stale snapshot
- Reason: home-page row of goal-appropriate titles in the app dialect
- Checks passed: ['content_available', 'content_dialect', 'content_not_quarantined', 'dialect_matches_app', 'eligibility', 'evidence_resolves', 'goal_measurable', 'no_duplicate_variant', 'not_duplicate_action', 'policy_scope', 'row_size']; failed: []
- Evidence: event:E0070368, profile:V-0010#row10, history:V-0010:completions=0, goal_rule:G01-e1, catalogue:T1395, catalogue:T0758, catalogue:T0385, catalogue:T0012
- Decided in 4980 ms; calls 1 model / 4 tool

### D-02911 · 2026-10-01T17:25:45Z · app_open → **PUBLISHED** `HOME_PAGE`
- Goal: G01 first_full_episode_3d (deadline 2026-10-04T12:35:00Z, continuing)
- Dialect: used d3 from app_setting; conflicts ['profile:d1', 'campaign_link:d5']
- Content: title:T1395, title:T0758, title:T0385, title:T0012, title:T0533, title:T1219
- Confidence 0.45: 2 dialect source(s) disagree with the app setting; subscription from a stale snapshot
- Reason: home-page row of goal-appropriate titles in the app dialect
- Checks passed: ['content_available', 'content_dialect', 'content_not_quarantined', 'dialect_matches_app', 'eligibility', 'evidence_resolves', 'goal_measurable', 'no_duplicate_variant', 'not_duplicate_action', 'policy_scope', 'row_size']; failed: []
- Evidence: event:E0069790, profile:V-0010#row10, history:V-0010:completions=0, goal_rule:G01-e1, catalogue:T1395, catalogue:T0758, catalogue:T0385, catalogue:T0012
- Decided in 4980 ms; calls 1 model / 4 tool

## Outcomes
- G01 (D-00470, treatment): **FAILED**: no qualifying success event inside the window; under rule at open: FAILED

## Learned
- 2026-10-11T18:00:01Z content_failed: {"goal": "G01", "titles": ["T1395", "T0758", "T0385", "T0012", "T0533", "T1219"], "action": "HOME_PAGE", "decision_id": "D-00470"}