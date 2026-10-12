"""CLI.

  python -m ottagent replay [--pack data/pack] [--out sample_run]   generate pack if missing, replay, judge, report
  python -m ottagent generate [--pack data/pack] [--seed 7]
  python -m ottagent explain V-0005 [--run sample_run] [--at 2026-10-01T14:11:00Z]
"""
import argparse
import json
import os
import sys

from .config import Config


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ottagent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--pack", default="data/pack")
    g.add_argument("--seed", type=int, default=7)
    r = sub.add_parser("replay")
    r.add_argument("--pack", default="data/pack")
    r.add_argument("--out", default="sample_run")
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("--workers", type=int, default=None)
    r.add_argument("--llm", choices=["mock", "anthropic"], default="mock")
    e = sub.add_parser("explain")
    e.add_argument("viewer")
    e.add_argument("--run", default="sample_run")
    e.add_argument("--at", default=None)
    a = ap.parse_args(argv)

    if a.cmd == "generate":
        from .datagen import generate
        print(json.dumps(generate(a.pack, a.seed), indent=1))
    elif a.cmd == "replay":
        from .datagen import generate
        from .final import final_report
        from .replay import run_replay
        from .reports import all_decisions, impact_report, latency_report, write_viewer_state
        if not os.path.exists(os.path.join(a.pack, "replay_script.jsonl")):
            print(f"no pack at {a.pack}; generating one (seed {a.seed})")
            generate(a.pack, a.seed)
        cfg = Config()
        if a.workers:
            cfg.workers = a.workers
        provider = None
        if a.llm == "anthropic":
            from .deps import AnthropicLLM
            provider = AnthropicLLM()
        store, agent, meta = run_replay(a.pack, a.out, cfg, provider)
        decisions = all_decisions(store)
        outcomes = [json.loads(l) for l in open(os.path.join(a.out, "outcomes.jsonl"), encoding="utf-8")]
        lat = latency_report(store, decisions, a.out, agent, cfg)
        imp = impact_report(store, decisions, outcomes, a.out, a.pack)
        write_viewer_state(store, a.out, sorted({d["viewer_id"] for d in decisions}))
        audits = final_report(store, decisions, outcomes, meta, lat, imp, a.out)
        from .explorer import build
        build(store, a.out, decisions, lat, imp, audits)
        store.commit()
        print(f"done. latency p95 {lat['decided_in_ms']['p95']} ms; ITT complete_3d "
              f"{imp['itt_complete_3d']['diff_pp']:+.1f} pp; reports in {a.out}/")
    elif a.cmd == "explain":
        from .reports import explain
        from .store import Store
        print(explain(Store(os.path.join(a.run, "state.sqlite")), a.viewer, a.at))
    return 0


if __name__ == "__main__":
    sys.exit(main())
