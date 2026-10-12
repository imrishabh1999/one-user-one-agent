"""Goal and intervention catalogues shipped in the synthetic pack.

The pack deliberately contains three defects the brief warns about:
  * G06 and G12 have underspecified eligibility text,
  * G11's success signal (watchlist_add) never appears in the event stream.
"""

GOALS = [
    {"id": "G01", "name": "first_full_episode_3d", "window_days": 3, "priority": 10,
     "eligibility": {"rule_id": "G01-e1", "text": "Signed-up viewer who has never completed an episode.",
                     "requires": ["signed_up", "no_completed_episode"]},
     "success": {"rule_id": "G01-s1", "version": 1, "text": "Any episode_complete event inside the window.",
                 "event_types": ["episode_complete"], "min_watch_pct": None}},
    {"id": "G02", "name": "first_play_24h", "window_days": 1, "priority": 12,
     "eligibility": {"rule_id": "G02-e1", "text": "Signed-up viewer with no play_start ever.",
                     "requires": ["signed_up", "no_play"]},
     "success": {"rule_id": "G02-s1", "version": 1, "text": "A play_start inside the window.",
                 "event_types": ["play_start"], "min_watch_pct": None}},
    {"id": "G03", "name": "second_episode_3d", "window_days": 3, "priority": 8,
     "eligibility": {"rule_id": "G03-e1", "text": "Viewer who has completed exactly one episode.",
                     "requires": ["exactly_one_completed"]},
     "success": {"rule_id": "G03-s1", "version": 1, "text": "An episode_complete for a different episode.",
                 "event_types": ["episode_complete"], "min_watch_pct": None, "distinct_episode": True}},
    {"id": "G04", "name": "finish_series_7d", "window_days": 7, "priority": 5,
     "eligibility": {"rule_id": "G04-e1", "text": "Viewer has watched at least half of a series but not its last episode.",
                     "requires": ["series_half_watched"]},
     "success": {"rule_id": "G04-s1", "version": 1, "text": "episode_complete of the last episode of that series.",
                 "event_types": ["episode_complete"], "min_watch_pct": None, "last_episode": True}},
    {"id": "G05", "name": "first_paid_plan_7d", "window_days": 7, "priority": 9,
     "eligibility": {"rule_id": "G05-e1", "text": "Viewer who has never paid and has completed at least one episode.",
                     "requires": ["never_paid", "completed_any"]},
     "success": {"rule_id": "G05-s1", "version": 1, "text": "A purchase event inside the window.",
                 "event_types": ["purchase"], "min_watch_pct": None}},
    {"id": "G06", "name": "trial_to_paid_before_expiry", "window_days": None, "priority": 11,
     "eligibility": {"rule_id": "G06-e1", "text": "Trial viewers whose trial is near expiry.",
                     "requires": ["on_trial", "trial_near_expiry"]},
     "success": {"rule_id": "G06-s1", "version": 1, "text": "A purchase before the trial ends.",
                 "event_types": ["purchase"], "min_watch_pct": None}},
    {"id": "G07", "name": "return_visit_7d", "window_days": 7, "priority": 4,
     "eligibility": {"rule_id": "G07-e1", "text": "Viewer with no app_open in the 14 days before this one.",
                     "requires": ["returning_after_14d_gap"]},
     "success": {"rule_id": "G07-s1", "version": 1, "text": "An app_open on a later local day inside the window.",
                 "event_types": ["app_open"], "min_watch_pct": None, "later_local_day": True}},
    {"id": "G08", "name": "search_to_play_1d", "window_days": 1, "priority": 7,
     "eligibility": {"rule_id": "G08-e1", "text": "Viewer searched in the last 24 h and played nothing after it.",
                     "requires": ["recent_search_without_play"]},
     "success": {"rule_id": "G08-s1", "version": 1, "text": "A play_start inside the window.",
                 "event_types": ["play_start"], "min_watch_pct": None}},
    {"id": "G09", "name": "second_dialect_title_14d", "window_days": 14, "priority": 2,
     "eligibility": {"rule_id": "G09-e1", "text": "Viewer with 3+ completions, all in one dialect.",
                     "requires": ["completed_3_single_dialect"]},
     "success": {"rule_id": "G09-s1", "version": 1, "text": "A play_start of a title in another dialect.",
                 "event_types": ["play_start"], "min_watch_pct": None, "other_dialect": True}},
    {"id": "G10", "name": "renew_before_expiry_5d", "window_days": 5, "priority": 11,
     "eligibility": {"rule_id": "G10-e1", "text": "Paid viewer whose plan expires within 5 days.",
                     "requires": ["paid", "sub_expires_within_5d"]},
     "success": {"rule_id": "G10-s1", "version": 1, "text": "A purchase inside the window.",
                 "event_types": ["purchase"], "min_watch_pct": None}},
    {"id": "G11", "name": "watchlist_add_2d", "window_days": 2, "priority": 3,
     "eligibility": {"rule_id": "G11-e1", "text": "Any viewer who browsed without playing.",
                     "requires": ["signed_up"]},
     "success": {"rule_id": "G11-s1", "version": 1, "text": "A watchlist_add event inside the window.",
                 "event_types": ["watchlist_add"], "min_watch_pct": None}},
    {"id": "G12", "name": "weekly_habit_3_sessions_7d", "window_days": 7, "priority": 3,
     "eligibility": {"rule_id": "G12-e1", "text": "Active viewers.", "requires": ["active_viewer"]},
     "success": {"rule_id": "G12-s1", "version": 1, "text": "app_open on 3 distinct local days in the window.",
                 "event_types": ["app_open"], "min_watch_pct": None, "distinct_days": 3}},
]

TEMPLATES = (
    [{"id": f"WA_TITLE_{d}", "channel": "WHATSAPP", "dialect": d, "approved": True, "vars": ["title_name"]}
     for d in ["d1", "d2", "d3", "d4"]]
    + [{"id": "WA_TITLE_d5", "channel": "WHATSAPP", "dialect": "d5", "approved": False, "vars": ["title_name"]}]
    + [{"id": f"PUSH_TITLE_{d}", "channel": "PUSH", "dialect": d, "approved": True, "vars": ["title_name"]}
       for d in ["d1", "d2", "d3", "d4", "d5", "d6"]]
    + [{"id": f"INAPP_PLAN_{d}", "channel": "IN_APP", "dialect": d, "approved": True, "vars": ["plan_name"]}
       for d in ["d1", "d2", "d3", "d4", "d5", "d6"]]
)

INTERVENTIONS = {
    "interventions": [
        {"id": "HOME_PAGE", "kind": "surface", "is_message": False, "min_titles": 3, "max_titles": 10,
         "rules": ["A row with fewer than three titles is not shown.", "Titles must exist in the viewer's app dialect."]},
        {"id": "HERO_SLOT", "kind": "surface", "is_message": False, "min_titles": 1, "max_titles": 1,
         "rules": ["Exactly one title, available in the viewer's app dialect."]},
        {"id": "IN_APP", "kind": "message", "is_message": True, "needs_session": True,
         "rules": ["Approved template only.", "Counts toward the one-message-per-day cap."]},
        {"id": "PUSH", "kind": "message", "is_message": True, "consent_field": "consent_push",
         "rules": ["Consent required.", "No sends 22:00-08:00 local.", "Approved template only."]},
        {"id": "WHATSAPP", "kind": "message", "is_message": True, "consent_field": "consent_whatsapp",
         "rules": ["Consent required.", "No sends 22:00-08:00 local.", "Template must be approved in the viewer's dialect."]},
        {"id": "NONE", "kind": "none", "is_message": False, "rules": ["Leave the viewer's experience unchanged."]},
    ],
    "templates": TEMPLATES,
    "policy": {"quiet_hours_local": "22:00-08:00", "max_messages_per_viewer_per_day": 1},
}
