"""Fault-signature rule engine.

Each rule scans the event stream for a known embedded failure signature and
returns Finding objects. Rules are intentionally small and independent so the
catalog can grow; `run_rules` just applies all registered rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .schema import Event, EventType


@dataclass
class Finding:
    rule: str
    severity: str            # "info" | "warn" | "error" | "critical"
    t: float                 # timestamp of the triggering event (or first one)
    message: str
    evidence: list[str] = field(default_factory=list)


Rule = Callable[[list[Event]], list[Finding]]
_REGISTRY: list[Rule] = []


def rule(fn: Rule) -> Rule:
    _REGISTRY.append(fn)
    return fn


@rule
def watchdog_reset(events: list[Event]) -> list[Finding]:
    out = []
    for e in events:
        if e.etype == EventType.WATCHDOG_RESET:
            out.append(Finding(
                "watchdog_reset", "critical", e.t,
                f"Watchdog timeout / reset at t={e.t:.3f}s "
                f"(cause={e.fields.get('reset_cause', '?')}, "
                f"last_task={e.fields.get('last_task', '?')})",
                evidence=[e.raw],
            ))
    return out


@rule
def brownout(events: list[Event]) -> list[Finding]:
    out = []
    for e in events:
        if e.etype == EventType.BROWNOUT:
            vbat = e.get_float("vbat")
            out.append(Finding(
                "brownout", "error", e.t,
                f"PMIC brownout at t={e.t:.3f}s (vbat={vbat}V) - check power rail "
                f"decoupling / supply droop under load.",
                evidence=[e.raw],
            ))
    return out


@rule
def crc_burst(events: list[Event], min_run: int = 3, window_s: float = 0.5) -> list[Finding]:
    """Flag *bursts* of CRC failures (>= min_run within window_s).

    Isolated CRC errors are normal on a noisy link; a burst suggests a real
    integrity problem (bad clocking, EMI, buffer overrun).
    """
    fails = [e for e in events if e.etype == EventType.CRC_FAIL]
    out = []
    i = 0
    while i < len(fails):
        j = i
        while j + 1 < len(fails) and fails[j + 1].t - fails[i].t <= window_s:
            j += 1
        run = j - i + 1
        if run >= min_run:
            out.append(Finding(
                "crc_burst", "error", fails[i].t,
                f"{run} CRC failures within {window_s}s starting at t={fails[i].t:.3f}s.",
                evidence=[fails[k].raw for k in range(i, j + 1)][:5],
            ))
            i = j + 1
        else:
            i += 1
    # also surface the aggregate rate as info
    if fails:
        out.append(Finding("crc_rate", "info", fails[0].t,
                           f"{len(fails)} total CRC failures observed.", []))
    return out


@rule
def task_starvation(events: list[Event], factor: float = 4.0) -> list[Finding]:
    """Detect a task not being dispatched for >> its nominal period.

    Classic symptom of priority inversion or a higher-priority task hogging the
    CPU. Nominal period is estimated as the median inter-dispatch interval.
    """
    from .analysis import _infer_nominal_period

    by_task: dict[str, list[float]] = {}
    for e in events:
        if e.etype == EventType.DISPATCH and e.task:
            by_task.setdefault(e.task, []).append(e.t)

    out = []
    for task, times in by_task.items():
        times = sorted(times)
        gaps = [b - a for a, b in zip(times, times[1:])]
        if len(gaps) < 3:
            continue
        nominal = _infer_nominal_period(gaps)
        for a, b in zip(times, times[1:]):
            gap = b - a
            if gap > factor * nominal:
                out.append(Finding(
                    "task_starvation", "warn", a,
                    f"Task '{task}' not dispatched for {gap * 1000:.1f}ms "
                    f"(~{gap / nominal:.1f}x its {nominal * 1000:.1f}ms period) "
                    f"starting at t={a:.3f}s - possible priority inversion.",
                    evidence=[],
                ))
    return out


def run_rules(events: list[Event]) -> list[Finding]:
    findings: list[Finding] = []
    for r in _REGISTRY:
        findings.extend(r(events))
    findings.sort(key=lambda f: f.t)
    return findings
