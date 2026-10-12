"""Replay the trigger script through the agent with a simulated clock and a pool of workers.

Latency model: each trigger waits in a FIFO queue until one of `cfg.workers` workers is free; the
decision then charges simulated costs for every tool and model call (deps.py). decided_in_ms =
queue wait + service time, measured from when the trigger reached us. This makes the evening peak,
the model outage and the slow store show up in the numbers deterministically.
"""
import heapq
import json
import os
import shutil
from collections import Counter, deque

from .agent import Agent
from .config import Config, iso, parse
from .deps import Environment, MockLLM
from .simulate import simulate
from .store import Store

DAY = 86_400


class JsonlSink:
    def __init__(self, out_dir):
        self.out_dir = out_dir
        self.files = {}

    def __call__(self, kind, rec):
        if kind not in self.files:
            self.files[kind] = open(os.path.join(self.out_dir, f"{kind}.jsonl"), "w", encoding="utf-8")
        self.files[kind].write(json.dumps(rec, default=str) + "\n")

    def close(self):
        for f in self.files.values():
            f.close()


def run_replay(pack_dir, out_dir, cfg=None, provider=None, db_path=None, judge_days=10, quiet=False):
    cfg = cfg or Config()
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    db_path = db_path or os.path.join(out_dir, "state.sqlite")
    store = Store(db_path)
    load_stats = store.load_pack(pack_dir)
    scenario = json.load(open(os.path.join(pack_dir, "_simulator", "scenario.json"), encoding="utf-8"))
    provider = provider or MockLLM(hallucinate_for=scenario["llm_hallucinates_eligibility_for"])
    env = Environment()
    sink = JsonlSink(out_dir)
    agent = Agent(store, cfg, env, provider, sink)
    log = lambda *a: None if quiet else print(*a)
    log(f"loaded pack: {load_stats}; quarantined titles: {agent.quarantined}")

    script = [json.loads(l) for l in open(os.path.join(pack_dir, "replay_script.jsonl"), encoding="utf-8")]
    heap, seq = [], 0
    for item in script:
        heapq.heappush(heap, (parse(item["at"]), seq, "item", item))
        seq += 1
    queue, free, busy_max = deque(), cfg.workers, 0
    state_change_decisions = []
    controls = []

    def dispatch(t):
        nonlocal free, seq, busy_max
        while free and queue:
            arr, item = queue.popleft()
            wait_ms = (t - arr) * 1000
            free -= 1
            res = agent.handle_trigger(item, start_ts=t, queue_wait_ms=wait_ms)
            service_s = max(0.05, (res.get("decided_in_ms", wait_ms) - wait_ms) / 1000)
            heapq.heappush(heap, (t + service_s, seq, "done", None))
            seq += 1
        busy_max = max(busy_max, len(queue))

    end_ts = 0
    while heap:
        t, _, kind, item = heapq.heappop(heap)
        end_ts = max(end_ts, t)
        if kind == "done":
            free += 1
            dispatch(t)
            continue
        k = item["kind"]
        if k == "trigger":
            queue.append((t, item))
            dispatch(t)
        elif k == "ingest":
            d = agent.on_event(item["event"], t)
            if d:
                state_change_decisions.append(d["decision_id"])
        elif k == "rule_update":
            agent.apply_rule_update(item["goal_id"], item["success"], t, item["reason"])
        elif k == "control":
            c = item["control"]
            if c == "llm_outage":
                env.llm_down.append((t, t + item["duration_s"]))
            elif c == "store_outage":
                env.store_down.append((t, t + item["duration_s"]))
            elif c == "store_slow":
                env.store_slow.append((t, t + item["duration_s"], item["factor"]))
            controls.append(item)
    replay_end = end_ts
    log(f"replay done at {iso(replay_end)}; llm stats {agent.llm.stats}")

    # ---- the world moves on: outcomes for the next days, then judge every due goal
    sim = simulate(store, pack_dir, replay_end, days=judge_days)
    judge_at = replay_end + judge_days * DAY
    agent.feed_complete_until = judge_at
    outcomes = agent.judge_due(judge_at)
    log(f"simulated {sim['events_generated']} outcome events; judged {len(outcomes)} goals")
    sink.close()

    meta = {"config": cfg.to_dict(), "pack": json.load(open(os.path.join(pack_dir, "pack_meta.json"), encoding="utf-8")),
            "load_stats": load_stats, "quarantined_titles": agent.quarantined, "llm_stats": agent.llm.stats,
            "replay_end": iso(replay_end), "judged_at": iso(judge_at), "simulation": sim,
            "state_change_decisions": state_change_decisions, "max_queue_len": busy_max,
            "controls_applied": controls, "scenario": scenario, "measurability": agent.measurable}
    json.dump(meta, open(os.path.join(out_dir, "run_meta.json"), "w", encoding="utf-8"), indent=1)
    return store, agent, meta
