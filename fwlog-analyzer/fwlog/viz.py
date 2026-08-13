"""Matplotlib visualizations.

matplotlib is an optional dependency: the analyze/report CLI paths work without
it, and only the `--plots` option imports it. Figures are saved to disk (no GUI)
so this runs headless in CI.
"""
from __future__ import annotations

from .analysis import TaskStats
from .anomaly import detect
from .schema import Event, EventType


def _require_mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def plot_task_timeline(events: list[Event], out_path: str) -> str:
    """Gantt-style dispatch timeline, one row per task, with fault markers."""
    plt = _require_mpl()
    tasks = sorted({e.task for e in events if e.task})
    row = {t: i for i, t in enumerate(tasks)}

    fig, ax = plt.subplots(figsize=(11, 0.8 * len(tasks) + 2))
    for e in events:
        if e.etype == EventType.DISPATCH and e.task:
            ax.plot(e.t, row[e.task], "|", color="#1f77b4", markersize=10)
    # fault markers spanning all rows
    for e in events:
        if e.etype == EventType.WATCHDOG_RESET:
            ax.axvline(e.t, color="red", lw=1.5, ls="--", label="wdt reset")
        elif e.etype == EventType.BROWNOUT:
            ax.axvline(e.t, color="orange", lw=1.0, ls=":", label="brownout")

    ax.set_yticks(list(row.values()))
    ax.set_yticklabels(tasks)
    ax.set_xlabel("time (s)")
    ax.set_title("RTOS task dispatch timeline")
    # de-duplicate legend labels
    handles, labels = ax.get_legend_handles_labels()
    seen = dict(zip(labels, handles))
    if seen:
        ax.legend(seen.values(), seen.keys(), loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def plot_period_jitter(task_stats: dict[str, TaskStats], out_path: str) -> str:
    """Histogram of measured periods per task; nominal marked with a line."""
    plt = _require_mpl()
    active = {k: v for k, v in task_stats.items() if v.periods_s}
    n = len(active)
    fig, axes = plt.subplots(n, 1, figsize=(9, 2.4 * n), squeeze=False)
    for ax, (name, ts) in zip(axes[:, 0], active.items()):
        ms = [p * 1000 for p in ts.periods_s]
        ax.hist(ms, bins=40, color="#2ca02c", alpha=0.8)
        ax.axvline(ts.nominal_period_s * 1000, color="black", ls="--",
                   label=f"nominal {ts.nominal_period_s*1000:.1f}ms")
        ax.set_title(f"{name}: jitter={ts.period_jitter_s*1e6:.1f}us, "
                     f"misses={ts.deadline_misses}")
        ax.set_xlabel("measured period (ms)")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def plot_anomalies(task_stats: dict[str, TaskStats], out_path: str,
                   method: str = "mad") -> str:
    """Period-vs-cycle scatter with statistical anomalies highlighted."""
    plt = _require_mpl()
    active = {k: v for k, v in task_stats.items() if len(v.periods_s) > 5}
    n = len(active)
    fig, axes = plt.subplots(n, 1, figsize=(10, 2.4 * n), squeeze=False)
    for ax, (name, ts) in zip(axes[:, 0], active.items()):
        ms = [p * 1000 for p in ts.periods_s]
        ax.plot(ms, ".", color="#7f7f7f", label="period")
        anoms = detect(ts.periods_s, method=method)
        if anoms:
            ax.plot([a.index for a in anoms], [a.value * 1000 for a in anoms],
                    "o", color="red", label="anomaly")
        ax.set_title(f"{name}: {len(anoms)} {method} anomalies")
        ax.set_xlabel("cycle #")
        ax.set_ylabel("period (ms)")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
