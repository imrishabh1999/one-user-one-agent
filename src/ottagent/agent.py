"""The per-viewer agent: understand -> choose goal -> decide -> verify -> act -> (later) judge and learn.

One logical agent per viewer: all of a viewer's state lives under their viewer_id in the store, the
store enforces at most one ACTIVE goal per viewer, and every decision for that viewer goes through
`_decide`, so no two components can pursue different goals for the same viewer.
"""
import json

from . import facts as factsmod
from . import goals as goalsmod
from . import planner, verify
from .catalogues import INTERVENTIONS
from .config import iso, local_day, parse
from .datagen import is_holdout
from .deps import INSTRUCTION_PATTERN, Budget, BudgetExceeded, DependencyError, LLMClient, ToolClient
from .judge import judge_goal, learn_from, qualifying_events

DAY = 86_400


class Agent:
    def __init__(self, store, cfg, env, provider, sink=None):
        self.store, self.cfg, self.env = store, cfg, env
        self.tools = ToolClient(store, env, cfg)
        self.llm = LLMClient(provider, env, cfg)
        self.sink = sink or (lambda kind, rec: None)
        self.templates = INTERVENTIONS["templates"]
        self.n_decisions = store.db.execute("SELECT COUNT(*) c FROM decisions").fetchone()["c"]
        self.quarantined = self._scan_catalogue()
        self.catalogue = store.titles()
        self.goal_rules = store.all_goal_rules()
        observed = {r["type"] for r in store.db.execute("SELECT DISTINCT type FROM events")}
        self.measurable = goalsmod.measurability(self.goal_rules, observed)
        self.feed_complete_until = 0.0

    # ------------------------------------------------------------------ setup
    def _scan_catalogue(self):
        """Catalogue text is data. Descriptions that read like instructions are quarantined, never prompted."""
        found = []
        for tid, t in self.store.titles().items():
            if INSTRUCTION_PATTERN.search(t.get("description", "")):
                self.store.quarantine(tid, "description contains instructions addressed to the agent")
                found.append(tid)
        return found

    # ------------------------------------------------------------------ public entry points
    def handle_trigger(self, trigger, start_ts, queue_wait_ms=0):
        """Process one app-open trigger. Idempotent on trigger_id and on event_id."""
        tid, ev = trigger["trigger_id"], trigger["event"]
        vid = ev["viewer_id"]
        # we cannot decide "before" the trigger reached us; never read evidence as of an earlier time
        start_ts = max(start_ts, parse(ev["received_ts"]))
        prior = self.store.seen_trigger(tid)
        if prior:
            rec = {"trigger_id": tid, "viewer_id": vid, "result": "DUPLICATE_TRIGGER_IGNORED",
                   "original_decision": prior["decision_id"], "at": iso(start_ts)}
            self.sink("trigger_log", rec)
            self.store.commit()
            return rec
        if not self.store.ingest_event(ev):
            self.store.record_trigger(tid, vid, start_ts, None)
            rec = {"trigger_id": tid, "viewer_id": vid, "result": "DUPLICATE_EVENT_IGNORED",
                   "event_id": ev["event_id"], "at": iso(start_ts)}
            self.sink("trigger_log", rec)
            self.store.commit()
            return rec
        self.feed_complete_until = max(self.feed_complete_until, start_ts)
        budget = Budget(self.cfg, queue_wait_ms)
        d = self._decide(vid, start_ts, budget, trigger_meta={"event": "app_open", "trigger_id": tid,
                                                              "event_id": ev["event_id"]}, trigger_event_id=ev["event_id"])
        self.store.record_trigger(tid, vid, start_ts, d["decision_id"])
        self.sink("trigger_log", {"trigger_id": tid, "viewer_id": vid, "result": d["status"],
                                  "decision_id": d["decision_id"], "at": iso(start_ts)})
        self.store.commit()
        return d

    def on_event(self, ev, at):
        """New data arrived (outside an app open). Re-plan only if it changes this viewer's situation."""
        if not self.store.ingest_event(ev):
            self.sink("trigger_log", {"event_id": ev["event_id"], "result": "DUPLICATE_EVENT_IGNORED", "at": iso(at)})
            return None
        self.feed_complete_until = max(self.feed_complete_until, at)
        vid = ev["viewer_id"]
        active = self.store.active_goal(vid)
        if ev["type"] not in ("purchase", "sign_up") or not active:
            self.store.commit()
            return None
        budget = Budget(self.cfg, 0)
        d = self._decide(vid, at, budget, trigger_meta={"event": "state_change", "cause": f"event:{ev['event_id']}",
                                                         "cause_type": ev["type"]}, trigger_event_id=None)
        self.store.commit()
        return d

    def apply_rule_update(self, goal_id, success, at, reason):
        """Corrected success condition: version the rule and touch only the goals that use it."""
        old = self.store.goal_rule(goal_id)
        self.store.add_goal_rule_version(goal_id, success, at)
        self.goal_rules[goal_id] = self.store.goal_rule(goal_id)
        affected = self.store.active_goals_by_goal_id(goal_id)
        closed = [dict(r) for r in self.store.db.execute(
            "SELECT * FROM goals WHERE goal_id=? AND status!='ACTIVE' AND verdict IS NOT NULL", (goal_id,))]
        for g in affected:
            self.store.close_goal(g["goal_instance_id"], "ACTIVE", None, None,
                                  note=f"success rule corrected v{old['success']['version']}->v{success['version']} at "
                                       f"{iso(at)}; will be judged under v{success['version']}, v{old['success']['version']} verdict also reported")
        rec = {"at": iso(at), "goal_id": goal_id, "from_version": old["success"]["version"], "to_version": success["version"],
               "reason": reason, "affected_active_goals": len(affected),
               "affected_decisions": [g["decision_id"] for g in affected],
               "already_judged_goals_to_rejudge": [g["goal_instance_id"] for g in closed],
               "viewers_not_touched": "all viewers without an open " + goal_id + " goal"}
        self.sink("corrections", rec)
        self.store.commit()
        return rec

    def judge_due(self, now, viewer_id=None):
        """Judge goals whose deadline + grace has passed (optionally for one viewer only)."""
        due = [g for g in self.store.goals_due(now - self.cfg.judge_grace_s)
               if viewer_id is None or g["viewer_id"] == viewer_id]
        outs = []
        for g in due:
            o = judge_goal(self.store, g, now, self.cfg, self.measurable, self.feed_complete_until)
            if o["verdict"] == "INCONCLUSIVE" and o["reason"].startswith("event feed not complete"):
                continue  # wait for data rather than judging early
            self.store.close_goal(g["goal_instance_id"], "JUDGED", now, o["verdict"])
            self.store.save_outcome(o)
            learn_from(self.store, o, g)
            self.sink("outcomes", o)
            outs.append(o)
        self.store.commit()
        return outs

    # ------------------------------------------------------------------ the decision
    def _memory(self, vid, now):
        return {"active_goal": self.store.active_goal(vid),
                "recent_decisions": [{"decision_id": d["decision_id"], "action": d["action"], "status": d["status"],
                                      "goal": (d.get("goal") or {}).get("id"), "at": d["trigger"].get("received_at")}
                                     for d in self.store.decisions_for(vid)[-5:]],
                "learnings": self.store.learnings_for(vid, now),
                "messages_today": self.store.messages_on_local_day(vid, local_day(now))}

    def _new_id(self):
        self.n_decisions += 1
        return f"D-{self.n_decisions:05d}"

    def _decide(self, vid, now, budget, trigger_meta, trigger_event_id):
        cfg = self.cfg
        arm = "holdout" if is_holdout(vid, cfg) else "treatment"
        d = {"decision_id": self._new_id(), "viewer_id": vid, "arm": arm, "_created_ts": now,
             "trigger": dict(trigger_meta, received_at=iso(now)), "goal": None, "action": "NONE",
             "dialect": {"used": None, "source": None, "conflicts": []}, "content": [], "confidence": None,
             "confidence_reason": None, "evidence": [], "assumptions": [], "facts": {},
             "checks": {"passed": [], "failed": []}, "model": {"used": [], "outputs_rejected": []},
             "rejected_proposals": [], "reason": None}
        try:
            events, meta = self.tools.call("read_events", budget, now, self.store.viewer_events, vid, now,
                                           cfg.clock_skew_threshold_s)
            prows = self.tools.call("read_profile", budget, now, self.store.profile_rows, vid)
            memory = self.tools.call("read_viewer_state", budget, now, self._memory, vid, now)
        except (DependencyError, BudgetExceeded) as ex:
            return self._finish(d, budget, "NO_ACTION", f"DEGRADED: {ex}; cannot assemble or verify evidence, so no action")

        trig = next((e for e in events if e["event_id"] == trigger_event_id), None) if trigger_event_id else None
        ctx = factsmod.assemble(vid, now, trig, events, meta, prows, memory, self.catalogue, cfg)
        d["facts"] = ctx["facts"]
        d["event_meta"] = meta
        if trig:
            d["trigger"]["event_age_s"] = int(trig["received_ts"] - trig["effective_ts"])
            d["trigger"]["effective_ts"] = iso(trig["effective_ts"])
            d["trigger"]["ts_source"] = trig["ts_source"]
            d["evidence"].append(f"event:{trig['event_id']}")
        fd = ctx["facts"]["dialect"]
        d["dialect"] = {"used": fd["value"], "source": fd["source"], "conflicts": fd["conflicts"], "note": fd["note"]}

        in_session = bool(trig) and (trig["received_ts"] - trig["effective_ts"]) <= cfg.stale_trigger_s
        d["in_session"] = in_session
        if trig and not in_session:
            return self._finish(d, budget, "NO_ACTION",
                                f"STALE_TRIGGER: app_open happened {d['trigger']['event_age_s'] // 3600} h before it reached us "
                                f"(buffered offline); the viewer is no longer in this session. Event stored for history only.")

        # ---- goal: keep, close or choose
        evals = goalsmod.evaluate(ctx, self.goal_rules, self.measurable, now)
        active = memory["active_goal"]
        if active:
            rule = self.goal_rules[active["goal_id"]]
            hits, _ = qualifying_events(self.store, active, rule, now, cfg)
            if hits:
                self._close_early(active, now, "SUCCEEDED", f"success signal already observed: event:{hits[0]['event_id']}")
                active = None
            elif active["opened_at"] <= now and not evals[active["goal_id"]]["eligible"]:
                premise = self._premise_was_false(active, events)
                self._close_early(active, now, "INCONCLUSIVE",
                                  ("premise false at decision time (late data): " + premise) if premise else
                                  f"viewer situation changed: {evals[active['goal_id']]['reasons']}")
                active = None
        if active:
            goal_rule = self.goal_rules[active["goal_id"]]
            goal_eval = evals[active["goal_id"]]
            deadline = active["deadline"]
            d["goal"] = {"id": active["goal_id"], "name": goal_rule["name"], "deadline": iso(deadline),
                         "instance": active["goal_instance_id"], "continuing": True,
                         "success_signal": goal_rule["success"], "opened_by": active["decision_id"]}
        else:
            eligible = sorted([g for g, r in evals.items() if r["eligible"]],
                              key=lambda g: -self.goal_rules[g]["priority"])
            d["goals_considered"] = {g: ("eligible" if r["eligible"] else "; ".join(r["reasons"])[:160]) for g, r in evals.items()}
            if len(eligible) >= 2 and self.goal_rules[eligible[0]]["priority"] - self.goal_rules[eligible[1]]["priority"] <= 1:
                choice = self._model_pick_goal(vid, eligible, ctx, budget, now, d)
                if choice:
                    eligible.remove(choice)
                    eligible.insert(0, choice)
            if not eligible:
                reasons = "; ".join(f"{g}: {r['reasons'][0]}" for g, r in sorted(evals.items()) if r["reasons"])[:600]
                return self._finish(d, budget, "NO_ACTION", f"NO_ELIGIBLE_GOAL: no goal can be chosen yet. {reasons}")
            gid = eligible[0]
            goal_rule = self.goal_rules[gid]
            goal_eval = evals[gid]
            deadline = goalsmod.deadline_for(goal_rule, ctx, now)
            d["goal"] = {"id": gid, "name": goal_rule["name"], "deadline": iso(deadline), "continuing": False,
                         "success_signal": goal_rule["success"]}
        d["evidence"] += [e for e in goal_eval["evidence"] if e]
        d["assumptions"] += goal_eval["assumptions"]
        for k in ("subscription", "dialect", "signup"):
            if ctx["facts"][k]["ref"]:
                d["evidence"].append(ctx["facts"][k]["ref"])

        if not fd["value"]:
            return self._finish(d, budget, "NO_ACTION", "NO_DIALECT_EVIDENCE: cannot pick content the viewer can watch",
                                open_goal=(not d["goal"].get("continuing"), deadline, ctx))

        # ---- plan
        excluded = {t for l in memory["learnings"] if l["kind"] == "content_failed" for t in l.get("titles", [])}
        proposals, cands = planner.propose(ctx, goal_rule, deadline, fd["value"], self.catalogue, self.templates, cfg,
                                           now, in_session, excluded, memory["messages_today"])
        used_llm = self._model_rank(vid, cands, proposals, budget, now, d)
        d["confidence"], d["confidence_reason"] = planner.confidence(ctx, goal_eval, used_llm)
        if fd["conflicts"]:
            d["assumptions"].append(f"content follows the app setting {fd['value']}; conflicting {fd['conflicts']} "
                                    "not used because the viewer sees the app-setting dialect")
        if trig:
            d["assumptions"].append("viewer is still in the session that produced this app_open")

        # ---- verify, walking down to smaller actions on failure
        chosen = None
        for p in proposals:
            cand = dict(d, action=p["action"], content=[f"title:{t}" for t in p["content"]],
                        template=p.get("template"), send_at=p.get("send_at"), target=vid)
            cand["evidence"] = d["evidence"] + [f"catalogue:{t}" for t in p["content"]]
            try:
                self.tools.call("verify_read", budget, now, lambda: None)
            except (DependencyError, BudgetExceeded) as ex:
                return self._finish(d, budget, "NO_ACTION", f"DEGRADED: verification unavailable ({ex}); no action")
            res = verify.verify(cand, self.store, cfg, now, self.measurable)
            if not res["failed"]:
                chosen, cand["checks"], cand["why"] = cand, res, p["why"]
                break
            d["rejected_proposals"].append({"action": p["action"], "failed": res["failed"]})
        if chosen is None:
            # even "do nothing for this goal" failed: the verifier disagrees with the goal itself
            last = d["rejected_proposals"][-1]["failed"]
            d["checks"] = {"passed": [], "failed": last}
            d["goal_rejected"] = d.pop("goal")
            d["goal"] = None
            return self._finish(d, budget, "NO_ACTION",
                                "VERIFIER_REJECTED_GOAL: independent check disagreed with the chosen goal "
                                f"({'; '.join(f['check'] + ': ' + f['detail'] for f in last)}); no goal opened")
        d = chosen
        d["evidence"] = list(dict.fromkeys(d["evidence"]))

        if budget.elapsed_ms > cfg.latency_fail_ms:
            return self._finish(d, budget, "EXPIRED", "decision exceeded the 5-minute limit; not published")
        if d["action"] == "NONE":
            reason = d["rejected_proposals"] and "ALL_PROPOSALS_FAILED_CHECKS" or "NOTHING_TO_DO"
            if d["goal"].get("continuing") and any(
                    f["check"] == "not_duplicate_action" for r in d["rejected_proposals"] for f in r["failed"]):
                reason = "ALREADY_IN_PLACE: the same intervention is already live for this viewer's active goal"
            return self._finish(d, budget, "NO_ACTION", reason, open_goal=(not d["goal"].get("continuing"), deadline, ctx))
        status = "HOLDOUT_SUPPRESSED" if arm == "holdout" else "PUBLISHED"
        return self._finish(d, budget, status, d.get("why"), open_goal=(not d["goal"].get("continuing"), deadline, ctx))

    # ------------------------------------------------------------------ model use (advisory only)
    def _model_pick_goal(self, vid, eligible, ctx, budget, now, d):
        out, st = self.llm.call("pick_goal", {"viewer_ref": vid, "eligible_goals": eligible,
                                              "summary": {"completions": ctx["features"]["n_completions"],
                                                          "subscription": ctx["facts"]["subscription"]["value"]}},
                                budget, now)
        d["model"]["used"].append({"task": "pick_goal", "status": st})
        if not out:
            return None
        g = out.get("goal_id")
        if g not in eligible:
            ok, why = verify.independent_eligibility(self.store, vid, g, now) if g in self.goal_rules else (False, "unknown goal")
            d["model"]["outputs_rejected"].append({"task": "pick_goal", "proposed": g, "claim": out.get("claim"),
                                                   "model_confidence": out.get("confidence"),
                                                   "why_rejected": f"not eligible by rules; independent check: {why}. "
                                                                   "Model text is not evidence."})
            return None
        return g

    def _model_rank(self, vid, cands, proposals, budget, now, d):
        """Ask the model to order titles only when there is a real choice (pool larger than the row)."""
        if len(cands) <= self.cfg.row_size:
            return False
        if budget.queue_wait_ms > self.cfg.queue_shed_ms:
            d["model"]["used"].append({"task": "rank_titles", "status": "skipped_load_shedding"})
            return False
        top = cands[:12]
        payload = {"viewer_ref": vid, "goal": d["goal"]["id"],
                   "candidates": [{k: c[k] for k in ("title_id", "genre", "format", "popularity", "genre_match", "description")}
                                  for c in top]}
        out, st = self.llm.call("rank_titles", payload, budget, now)
        d["model"]["used"].append({"task": "rank_titles", "status": st})
        if not out:
            return False
        if out.get("proposed_extra_action"):
            d["model"]["outputs_rejected"].append({"task": "rank_titles", "proposed": out["proposed_extra_action"],
                                                   "why_rejected": "model proposed an action outside the decision schema "
                                                                   "(broadcast); only per-viewer verified actions exist"})
        claim = out.get("goal_claim")
        if claim and claim.get("goal_id") != d["goal"]["id"]:
            g = claim.get("goal_id")
            ok, why = verify.independent_eligibility(self.store, vid, g, now) if g in self.goal_rules else (False, "unknown goal")
            d["model"]["outputs_rejected"].append({
                "task": "rank_titles", "proposed": f"switch goal to {g}", "claim": claim.get("claim"),
                "model_confidence": claim.get("confidence"),
                "why_rejected": ("no supporting event; independent eligibility check: " + why if not ok else
                                 "goal changes only through the rule-based goal step, not model text") +
                                ". Model text is never evidence."})
        allowed = {c["title_id"] for c in top}
        order = [t for t in out.get("order", []) if t in allowed]
        dropped = [t for t in out.get("order", []) if t not in allowed]
        if dropped:
            d["model"]["outputs_rejected"].append({"task": "rank_titles", "proposed": dropped,
                                                   "why_rejected": "titles outside the verified candidate set"})
        order += [c["title_id"] for c in top if c["title_id"] not in order]
        for p in proposals:
            if p["action"] == "HOME_PAGE":
                p["content"] = order[: self.cfg.row_size]
            if p["action"] == "HERO_SLOT" and "series" not in p["why"]:
                p["content"] = order[:1]
        return True

    # ------------------------------------------------------------------ helpers
    def _premise_was_false(self, active, events):
        late = [e for e in events if e["effective_ts"] < active["opened_at"] <= e["received_ts"]]
        if late:
            e = late[0]
            return (f"{e['type']} event:{e['event_id']} happened at {iso(e['effective_ts'])} but arrived at "
                    f"{iso(e['received_ts'])}, after decision {active['decision_id']}")
        return None

    def _close_early(self, g, now, verdict, reason):
        self.store.close_goal(g["goal_instance_id"], "CLOSED_EARLY", now, verdict, note=reason)
        o = {"goal_instance_id": g["goal_instance_id"], "viewer_id": g["viewer_id"], "goal_id": g["goal_id"],
             "decision_id": g["decision_id"], "arm": g["arm"], "opened_at": iso(g["opened_at"]),
             "deadline": iso(g["deadline"]), "judged_at": iso(now), "judged_at_ts": now, "verdict": verdict,
             "reason": reason, "closed_early": True, "evidence": []}
        if verdict == "SUCCEEDED":
            o["attribution"] = "holdout_no_action" if g["arm"] == "holdout" else (
                "acted" if g["data"].get("acted") else "no_action_taken")
        self.store.save_outcome(o)
        learn_from(self.store, o, g)
        self.store.add_learning(g["viewer_id"], now, "plan_revised", {"closed": g["goal_id"], "verdict": verdict, "reason": reason})
        self.sink("outcomes", o)

    def _finish(self, d, budget, status, reason, open_goal=None):
        d["status"] = status
        d["reason"] = reason
        d["decided_in_ms"] = int(budget.elapsed_ms)
        d["budget"] = budget.summary()
        d["budget"]["calls"] = budget.calls
        d["decided_at"] = iso(d["_created_ts"] + budget.elapsed_ms / 1000)
        d["within_latency_target"] = budget.elapsed_ms <= self.cfg.latency_target_ms
        if d.get("goal"):
            d["goal"]["judged_by"] = {"deadline": d["goal"]["deadline"], "signal": d["goal"]["success_signal"]["event_types"],
                                      "rule": d["goal"]["success_signal"]["rule_id"]}
        if open_goal and open_goal[0] and d.get("goal"):
            _, deadline, ctx = open_goal
            gi = {"goal_instance_id": f"GI-{d['decision_id']}", "viewer_id": d["viewer_id"], "goal_id": d["goal"]["id"],
                  "opened_at": d["_created_ts"], "deadline": deadline, "decision_id": d["decision_id"], "arm": d["arm"],
                  "success_rule_version": d["goal"]["success_signal"]["version"],
                  "action": d["action"], "acted": status == "PUBLISHED",
                  "content_titles": [c.split(":", 1)[1] for c in d["content"]], "dialect": d["dialect"]["used"],
                  "baseline_completed": ctx["features"]["completed_eps"],
                  "series_id": (ctx["features"]["half_watched_series"] or [None])[0]}
            if gi["series_id"]:
                gi["series_last_ep"] = self.catalogue[gi["series_id"]]["episodes"]
            self.store.open_goal(gi)
            d["goal"]["instance"] = gi["goal_instance_id"]
        if status == "PUBLISHED" and d["action"] != "NONE":
            a = {"action_id": f"A-{d['decision_id']}", "decision_id": d["decision_id"], "viewer_id": d["viewer_id"],
                 "channel": d["action"], "is_message": d["action"] in verify.MESSAGE_ACTIONS,
                 "publish_at": d["_created_ts"] + budget.elapsed_ms / 1000, "content": d["content"],
                 "dialect": d["dialect"]["used"], "template": (d.get("template") or {}).get("id"),
                 "send_at": d.get("send_at"), "goal": d["goal"]["id"]}
            if a["is_message"]:
                from .config import parse
                a["local_day"] = local_day(parse(a["send_at"]))
            a["published_at"] = iso(a["publish_at"])
            self.store.save_action(a)
            self.sink("actions", a)
        elif d.get("goal") and d["goal"].get("continuing") is False and status == "NO_ACTION" and open_goal:
            pass
        d.pop("why", None)
        self.store.save_decision(d)
        out = {k: v for k, v in d.items() if not k.startswith("_")}
        self.sink("decisions", out)
        return out
