"""All tunable limits in one place. Every number here is a policy choice, not a fact."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class Config:
    # budgets (brief, section 7)
    max_model_calls: int = 8
    max_tool_calls: int = 20
    latency_target_ms: int = 60_000      # publish within 60 s of trigger
    latency_fail_ms: int = 300_000       # > 5 min counts as failure
    soft_budget_ms: int = 40_000         # beyond this the agent stops spending on optional calls
    queue_shed_ms: int = 15_000          # if the trigger waited this long in queue, skip the model

    # dependencies (simulated cost per call, used in replay to model latency)
    tool_call_ms: int = 120
    llm_call_ms: int = 4_500
    llm_timeout_ms: int = 8_000
    store_timeout_ms: int = 3_000
    breaker_failures: int = 3            # consecutive failures that open the circuit
    breaker_cooldown_s: int = 120
    workers: int = 4                     # concurrent decision workers in replay

    # freshness / staleness
    stale_trigger_s: int = 1_800         # an app_open older than 30 min: viewer has left the session
    app_setting_fresh_s: int = 7 * 86_400
    clock_skew_threshold_s: int = 3_600  # median device-vs-server offset above this => skewed clock
    duplicate_action_window_s: int = 1_800

    # messaging policy
    quiet_start_hour: int = 22
    quiet_end_hour: int = 8
    max_messages_per_local_day: int = 1
    morning_send_hour: int = 9

    # content
    min_row_titles: int = 3
    row_size: int = 6

    # measurement
    holdout_pct: int = 10
    holdout_salt: str = "pilot-2026-10"
    judge_grace_s: int = 6 * 3_600       # late events accepted this long after a deadline

    def to_dict(self):
        return asdict(self)


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def local_hour(ts: float) -> float:
    d = datetime.fromtimestamp(ts, IST)
    return d.hour + d.minute / 60


def local_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, IST).strftime("%Y-%m-%d")


def in_quiet_hours(ts: float, cfg: Config) -> bool:
    h = local_hour(ts)
    return h >= cfg.quiet_start_hour or h < cfg.quiet_end_hour


def next_allowed_send(ts: float, cfg: Config) -> float:
    """First moment at or after ts that is outside quiet hours (sends at morning_send_hour)."""
    if not in_quiet_hours(ts, cfg):
        return ts
    d = datetime.fromtimestamp(ts, IST)
    target = d.replace(hour=cfg.morning_send_hour, minute=0, second=0, microsecond=0)
    if d.hour >= cfg.quiet_start_hour:
        target += timedelta(days=1)
    return target.timestamp()
