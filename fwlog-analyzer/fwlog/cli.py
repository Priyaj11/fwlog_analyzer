"""Command-line interface.

Subcommands:
    generate   write a synthetic device log (with injectable faults)
    parse      parse a log and print event / parse-rate summary
    analyze    full timing + fault analysis, printed as a report
    report     analyze and also write plots + a report file

Examples
--------
    python -m fwlog generate device.log --duration 8 --seed 3
    python -m fwlog analyze device.log
    python -m fwlog report device.log --outdir out/
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .analysis import analyze_tasks, schedulability
from .faults import run_rules
from .generator import generate
from .parser import ParseStats, parse_file
from .report import build_report


def _cmd_generate(args) -> int:
    truth = generate(args.path, duration_s=args.duration, seed=args.seed,
                     inject=not args.clean)
    print(f"wrote {args.path}: {truth['total_lines']} lines")
    print(f"injected ground truth: {truth}")
    return 0


def _cmd_parse(args) -> int:
    stats = ParseStats()
    events = parse_file(args.path, stats)
    print(f"parsed {stats.parsed}/{stats.total} lines "
          f"({stats.parse_rate*100:.1f}%), {stats.unparsed} unparsed")
    from collections import Counter
    c = Counter(e.etype.value for e in events)
    for k, v in c.most_common():
        print(f"  {k:<14} {v}")
    return 0


def _analyze(path):
    stats = ParseStats()
    events = parse_file(path, stats)
    task_stats = analyze_tasks(events)
    sched = schedulability(task_stats)
    findings = run_rules(events)
    return events, stats, task_stats, sched, findings


def _cmd_analyze(args) -> int:
    _, stats, task_stats, sched, findings = _analyze(args.path)
    print(build_report(stats, task_stats, sched, findings))
    return 0


def _cmd_report(args) -> int:
    import os
    events, stats, task_stats, sched, findings = _analyze(args.path)
    os.makedirs(args.outdir, exist_ok=True)
    report_txt = build_report(stats, task_stats, sched, findings)
    rp = os.path.join(args.outdir, "report.txt")
    with open(rp, "w") as fh:
        fh.write(report_txt)
    written = [rp]
    if not args.no_plots:
        try:
            from . import viz
            written.append(viz.plot_task_timeline(
                events, os.path.join(args.outdir, "timeline.png")))
            written.append(viz.plot_period_jitter(
                task_stats, os.path.join(args.outdir, "jitter.png")))
            written.append(viz.plot_anomalies(
                task_stats, os.path.join(args.outdir, "anomalies.png"),
                method=args.method))
        except ImportError:
            print("matplotlib not installed; skipping plots", file=sys.stderr)
    print(report_txt)
    print("\nwrote:")
    for w in written:
        print(f"  {w}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fwlog", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"fwlog {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write a synthetic device log")
    g.add_argument("path")
    g.add_argument("--duration", type=float, default=5.0, help="seconds")
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("--clean", action="store_true", help="no fault injection")
    g.set_defaults(func=_cmd_generate)

    pa = sub.add_parser("parse", help="parse and summarize events")
    pa.add_argument("path")
    pa.set_defaults(func=_cmd_parse)

    an = sub.add_parser("analyze", help="print full analysis report")
    an.add_argument("path")
    an.set_defaults(func=_cmd_analyze)

    rp = sub.add_parser("report", help="analyze + write report and plots")
    rp.add_argument("path")
    rp.add_argument("--outdir", default="out")
    rp.add_argument("--method", default="mad", choices=["mad", "zscore"])
    rp.add_argument("--no-plots", action="store_true")
    rp.set_defaults(func=_cmd_report)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
