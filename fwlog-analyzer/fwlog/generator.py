"""Synthetic RTOS/UART log generator with fault injection.

Real embedded logs are hard to share (proprietary, noisy, huge), so we model
a small fixed-priority preemptive RTOS running a handful of periodic tasks and
emit a UART-style text log. Faults can be injected deterministically via the
RNG seed so tests and demos are reproducible.

Emitted line formats are intentionally *heterogeneous* (seconds vs. millisecond
timestamps, single-letter vs. word severities, occasional un-parseable debug
prints) to exercise the parser's grammar fallback logic.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class TaskSpec:
    name: str
    prio: int
    period_ms: float       # nominal release period
    exec_us_mean: float    # nominal execution time
    exec_us_std: float


DEFAULT_TASKS = [
    TaskSpec("sensor_poll", prio=3, period_ms=10.0, exec_us_mean=800, exec_us_std=60),
    TaskSpec("ctrl_loop",   prio=2, period_ms=20.0, exec_us_mean=2500, exec_us_std=200),
    TaskSpec("telemetry",   prio=1, period_ms=100.0, exec_us_mean=6000, exec_us_std=800),
]


def _fmt_time_s(t: float) -> str:
    return f"[{t:11.6f}]"


def _fmt_time_ms(t: float) -> str:
    return f"{t * 1000:.0f} ms"


def generate(
    path: str,
    duration_s: float = 5.0,
    tasks: list[TaskSpec] | None = None,
    seed: int = 0,
    inject: bool = True,
) -> dict:
    """Write a synthetic log to `path`.

    Returns a dict of ground-truth injected faults so tests can assert that the
    analyzer recovers them.
    """
    rng = random.Random(seed)
    tasks = tasks or DEFAULT_TASKS
    lines: list[tuple[float, str]] = []
    truth = {"exec_spikes": 0, "watchdog_resets": 0, "brownouts": 0, "crc_fails": 0}

    # --- periodic task activity ---------------------------------------------
    for spec in tasks:
        period_s = spec.period_ms / 1000.0
        t = 0.0
        cycle = 0
        while t < duration_s:
            # release jitter: a few percent of the period
            jitter = rng.gauss(0, period_s * 0.02)
            t_disp = max(0.0, t + jitter)
            exec_us = max(50.0, rng.gauss(spec.exec_us_mean, spec.exec_us_std))

            # Fault injection: occasional execution-time spike. Large spikes
            # overrun the task period (a true deadline miss); smaller ones are
            # subtle timing outliers meant to be caught statistically.
            if inject and rng.random() < 0.01:
                exec_us *= rng.uniform(4, 12)
                truth["exec_spikes"] += 1

            t_done = t_disp + exec_us / 1e6
            lines.append((t_disp,
                          f"{_fmt_time_s(t_disp)} INFO  sched: task={spec.name} "
                          f"prio={spec.prio} dispatch cycle={cycle}"))
            lines.append((t_done,
                          f"{_fmt_time_s(t_done)} INFO  sched: task={spec.name} "
                          f"prio={spec.prio} complete exec_us={exec_us:.0f}"))
            cycle += 1
            t += period_s

    # --- watchdog: fed every 50 ms; inject a timeout+reset -------------------
    t = 0.0
    wdt_count = 0
    reset_at = duration_s * 0.6 if inject else None
    did_reset = False
    while t < duration_s:
        if reset_at is not None and not did_reset and t >= reset_at:
            lines.append((t, f"{_fmt_time_s(t)} ERROR wdt: WATCHDOG TIMEOUT "
                             f"reset_cause=WDT last_task=ctrl_loop"))
            lines.append((t + 0.002, f"{_fmt_time_ms(t + 0.002)}  WARN  boot: ==== "
                                     f"SYSTEM RESET ==== rev=1.4.2 cause=WDT"))
            truth["watchdog_resets"] += 1
            did_reset = True
            wdt_count = 0
        else:
            lines.append((t, f"{_fmt_time_s(t)} DEBUG wdt: fed count={wdt_count}"))
            wdt_count += 1
        t += 0.050

    # --- PMIC brownout warnings (rare, undervoltage) -------------------------
    if inject:
        for _ in range(rng.randint(1, 3)):
            bt = rng.uniform(0, duration_s)
            vbat = rng.uniform(2.75, 2.95)
            lines.append((bt, f"{_fmt_time_s(bt)} ERROR pmic: brownout detected "
                              f"vbat={vbat:.2f}V thresh=3.00V"))
            truth["brownouts"] += 1

    # --- comm task frames with occasional CRC failures ----------------------
    t, seq = 0.0, 0
    while t < duration_s:
        crc_ok = not (inject and rng.random() < 0.03)
        status = "OK" if crc_ok else "FAIL"
        if not crc_ok:
            truth["crc_fails"] += 1
        # note the mixed millisecond-timestamp format here on purpose
        lines.append((t, f"{_fmt_time_ms(t)}  INFO net: frame seq={seq} "
                         f"len={rng.randint(16, 256)} crc={status}"))
        seq += 1
        t += 0.025

    # --- sprinkle a few genuinely un-parseable lines ------------------------
    if inject:
        for _ in range(5):
            jt = rng.uniform(0, duration_s)
            lines.append((jt, ">>> raw dump 0xDEADBEEF 0x0000 0xFFFF garbage"))

    # sort by time and strip the sort key; ordering is how a real UART stream
    # would arrive.  Unparseable lines get a synthetic key so they interleave.
    lines.sort(key=lambda x: x[0])
    with open(path, "w") as fh:
        for _, text in lines:
            fh.write(text + "\n")

    truth["total_lines"] = len(lines)
    return truth


if __name__ == "__main__":  # pragma: no cover
    t = generate("device.log", duration_s=5.0, seed=1)
    print("ground truth:", t)
