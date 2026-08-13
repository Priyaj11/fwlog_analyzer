"""Timing analysis for periodic RTOS tasks.

Given the event stream, we reconstruct each task's release schedule and derive
the metrics an embedded engineer actually cares about:

* period jitter    - std-dev of measured inter-dispatch intervals
* execution time   - mean / p95 / max from the `exec_us` field on COMPLETE events
* deadline misses  - implicit-deadline model (deadline == period)
* CPU utilization  - sum(exec_time)/window and the Liu & Layland bound check

These are standard real-time-systems quantities; see the technical writeup for
the model assumptions.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .anomaly import detect
from .schema import Event, EventType


@dataclass
class TaskStats:
    name: str
    n_cycles: int = 0
    nominal_period_s: float = 0.0
    period_mean_s: float = 0.0
    period_jitter_s: float = 0.0      # std-dev of measured periods
    exec_mean_us: float = 0.0
    exec_p95_us: float = 0.0
    exec_max_us: float = 0.0
    deadline_misses: int = 0          # response-time or period-gap violations
    exec_anomalies: int = 0           # statistical outliers in execution time
    utilization: float = 0.0          # fraction of CPU consumed by this task
    periods_s: list[float] = field(default_factory=list)
    exec_us: list[float] = field(default_factory=list)

    @property
    def miss_rate(self) -> float:
        return self.deadline_misses / self.n_cycles if self.n_cycles else 0.0


def _percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _infer_nominal_period(periods: list[float]) -> float:
    """Robust nominal period estimate = median of measured intervals.

    The median rejects the outliers created by deadline misses / skipped
    cycles, which a plain mean would be dragged toward.
    """
    return statistics.median(periods) if periods else 0.0


def analyze_tasks(events: list[Event], window_s: float | None = None) -> dict[str, TaskStats]:
    """Compute per-task timing statistics from the event stream."""
    dispatches: dict[str, list[float]] = {}
    execs: dict[str, list[float]] = {}
    for e in events:
        if e.etype == EventType.DISPATCH and e.task:
            dispatches.setdefault(e.task, []).append(e.t)
        elif e.etype == EventType.COMPLETE and e.task:
            ex = e.get_float("exec_us")
            if ex is not None:
                execs.setdefault(e.task, []).append(ex)

    if window_s is None:
        all_t = [e.t for e in events]
        window_s = (max(all_t) - min(all_t)) if all_t else 0.0

    out: dict[str, TaskStats] = {}
    for task, times in dispatches.items():
        times = sorted(times)
        periods = [b - a for a, b in zip(times, times[1:])]
        ts = TaskStats(name=task, n_cycles=len(times), periods_s=periods)
        nominal = 0.0
        if periods:
            nominal = _infer_nominal_period(periods)
            ts.nominal_period_s = nominal
            ts.period_mean_s = statistics.fmean(periods)
            ts.period_jitter_s = statistics.pstdev(periods) if len(periods) > 1 else 0.0

        ex = execs.get(task, [])
        ts.exec_us = ex
        if ex:
            ts.exec_mean_us = statistics.fmean(ex)
            ts.exec_p95_us = _percentile(ex, 0.95)
            ts.exec_max_us = max(ex)
            if window_s > 0:
                ts.utilization = (sum(ex) / 1e6) / window_s
            # statistical outliers in execution time (robust MAD detector)
            ts.exec_anomalies = len(detect(ex, method="mad"))

        # Implicit-deadline miss model (deadline == period). A miss occurs when
        # either (a) the response time exceeds the deadline -- here the job's
        # execution time overruns its own period -- or (b) a release slips so
        # far that the inter-dispatch interval exceeds 1.5x the nominal period.
        if nominal > 0:
            rt_misses = sum(1 for e in ex if e / 1e6 > nominal)
            gap_misses = sum(1 for p in periods if p > 1.5 * nominal)
            ts.deadline_misses = rt_misses + gap_misses
        out[task] = ts
    return out


@dataclass
class SchedulabilitySummary:
    total_utilization: float
    n_tasks: int
    ll_bound: float          # Liu & Layland utilization bound
    schedulable_ll: bool     # passes the sufficient (not necessary) LL test

    @property
    def overloaded(self) -> bool:
        return self.total_utilization > 1.0


def schedulability(task_stats: dict[str, TaskStats]) -> SchedulabilitySummary:
    """Liu & Layland RM utilization-bound check.

    U <= n(2^(1/n) - 1) is *sufficient* for schedulability under rate-monotonic
    priorities. Above the bound the set may still be schedulable, but it warrants
    a closer look; above 1.0 it is definitely overloaded.
    """
    n = len(task_stats)
    total_u = sum(t.utilization for t in task_stats.values())
    ll = n * (2 ** (1 / n) - 1) if n else 1.0
    return SchedulabilitySummary(
        total_utilization=total_u,
        n_tasks=n,
        ll_bound=ll,
        schedulable_ll=total_u <= ll,
    )
