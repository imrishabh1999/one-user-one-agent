# Audit: V-3053

## Evidence received (8 events)
- E0041255 `sign_up` happened 2026-09-09T11:11:27Z (device clock), received 2026-09-09T11:11:52Z
- E0070228 `app_open` happened 2026-09-30T22:30:57Z (device clock), received 2026-10-01T13:00:00Z
- S0007578 `app_open` happened 2026-10-03T19:18:27Z (device clock), received 2026-10-03T19:18:43Z
- S0007579 `play_start` happened 2026-10-03T19:18:57Z (device clock), received 2026-10-03T19:19:28Z
- S0007580 `app_open` happened 2026-10-04T20:44:22Z (device clock), received 2026-10-04T20:44:49Z
- S0007581 `play_start` happened 2026-10-04T20:44:52Z (device clock), received 2026-10-04T20:44:54Z
- S0007582 `app_open` happened 2026-10-09T20:48:11Z (device clock), received 2026-10-09T20:48:28Z
- S0007583 `app_open` happened 2026-10-10T18:56:10Z (device clock), received 2026-10-10T18:56:57Z

Profile snapshot rows: 1 (newest updated 2026-09-29T18:30:00Z: status never_paid, dialect d2)

## Decisions

### D-00647 · 2026-10-01T13:00:00Z · app_open → **NO_ACTION** `NONE`
- Goal: none
- Dialect: used d2 from app_setting; conflicts []
- Confidence None: None
- Reason: STALE_TRIGGER: app_open happened 14 h before it reached us (buffered offline); the viewer is no longer in this session. Event stored for history only.
- Checks passed: []; failed: []
- Evidence: event:E0070228
- Decided in 360 ms; calls 0 model / 3 tool

## Outcomes

## Learned