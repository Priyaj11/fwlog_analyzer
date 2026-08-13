"""Assemble a human-readable analysis report (plain text / markdown-ish)."""
from __future__ import annotations

from .analysis import SchedulabilitySummary, TaskStats
from .faults import Finding
from .parser import ParseStats


def build_report(stats: ParseStats, task_stats: dict[str, TaskStats],
                 sched: SchedulabilitySummary, findings: list[Finding]) -> str:
    L: list[str] = []
    add = L.append

    add("=" * 68)
    add("  FWLOG ANALYSIS REPORT")
    add("=" * 68)
    add("")
    add(f"Lines: {stats.total}  parsed: {stats.parsed}  "
        f"unparsed: {stats.unparsed}  ({stats.parse_rate*100:.1f}% parsed)")
    add("")

    add("-- TASK TIMING " + "-" * 53)
    hdr = f"{'task':<14}{'cycles':>7}{'period(ms)':>12}{'jitter(us)':>12}" \
          f"{'exec p95(us)':>14}{'U':>7}{'misses':>8}{'anom':>6}"
    add(hdr)
    add("-" * len(hdr))
    for name, ts in sorted(task_stats.items()):
        add(f"{name:<14}{ts.n_cycles:>7}{ts.nominal_period_s*1000:>12.3f}"
            f"{ts.period_jitter_s*1e6:>12.1f}{ts.exec_p95_us:>14.1f}"
            f"{ts.utilization:>7.2f}{ts.deadline_misses:>8}{ts.exec_anomalies:>6}")
    add("")

    add("-- SCHEDULABILITY " + "-" * 50)
    add(f"Total CPU utilization U = {sched.total_utilization:.3f} "
        f"over {sched.n_tasks} tasks")
    add(f"Liu & Layland RM bound  = {sched.ll_bound:.3f}")
    if sched.overloaded:
        add("VERDICT: OVERLOADED (U > 1.0) - task set is not schedulable.")
    elif sched.schedulable_ll:
        add("VERDICT: schedulable (passes sufficient LL utilization test).")
    else:
        add("VERDICT: inconclusive - U above LL bound; run response-time analysis.")
    add("")

    add("-- FAULT FINDINGS " + "-" * 50)
    if not findings:
        add("No fault signatures detected.")
    else:
        order = {"critical": 0, "error": 1, "warn": 2, "info": 3}
        for f in sorted(findings, key=lambda x: (order.get(x.severity, 9), x.t)):
            add(f"[{f.severity.upper():<8}] {f.message}")
            for ev in f.evidence:
                add(f"           | {ev}")
    add("")
    add("=" * 68)
    return "\n".join(L)
