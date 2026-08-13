# fwlog — Firmware/RTOS Log Analyzer & Timing-Anomaly Detector

> running this step by step.

A command-line tool that ingests messy embedded-system serial (UART) logs, reconstructs the real-time task schedule, and automatically flags **timing anomalies** and **known fault signatures** — the kind of bug hunting an embedded engineer normally does by squinting at a scrolling terminal. It parses heterogeneous log formats, computes per-task period/jitter/execution statistics, applies a rate-monotonic schedulability check, runs robust statistical outlier detection on the timing series, and matches a catalog of fault signatures (watchdog resets, brown-outs, CRC bursts, task starvation).

```
raw UART log ──▶ parser ──▶ Event stream ──┬──▶ timing analysis ──▶ schedulability
 (mixed formats)  (grammar)   (typed)       ├──▶ statistical anomaly detection
                                            └──▶ fault-signature rule engine ──▶ report + plots
```

## Why this is non-trivial

* **Grammar-based parsing** of three interleaved timestamp/severity formats with
  a fallback path and unparsed-line accounting — adding a new firmware's format
  is one regex, not a rewrite.
* **Real-time-systems analysis**: implicit-deadline miss detection, period
  jitter, and a Liu & Layland rate-monotonic utilization-bound check.
* **Robust statistics**: a median/MAD outlier detector (breakdown point ~50%)
  that survives the very spikes that break a naive rolling z-score (masking).
* **Reproducible fault injection**: a seeded RTOS log generator produces ground
  truth so the whole pipeline is testable end-to-end.

## Install

Core analysis needs **only the Python standard library** — nothing to install.
For the plots and tests:

```bash
python3 -m pip install matplotlib pytest
```

Requires Python >= 3.9.

## Usage

```bash
# 1. Generate a synthetic device log with injected faults (reproducible via --seed)
python3 -m fwlog generate device.log --duration 8 --seed 3

# 2. Quick parse summary (event-type histogram + parse rate)
python3 -m fwlog parse device.log

# 3. Full timing + fault analysis report to stdout
python3 -m fwlog analyze device.log

# 4. Analysis + report file + PNG plots
python3 -m fwlog report device.log --outdir out/ --method mad
```

Point it at a real log instead — any log whose lines match the supported
formats will parse; unmatched lines are counted and skipped.

### Example report

```
-- TASK TIMING --------------------------------------------------------
task           cycles  period(ms)  jitter(us)  exec p95(us)      U  misses  anom
--------------------------------------------------------------------------------
ctrl_loop         401      20.026       526.5        2834.0   0.14       2     7
sensor_poll       801       9.992       268.6         901.0   0.08       0    20
telemetry          81     100.450      2910.8        7293.0   0.06       0     0

-- SCHEDULABILITY --------------------------------------------------
Total CPU utilization U = 0.287 over 3 tasks
Liu & Layland RM bound  = 0.780
VERDICT: schedulable (passes sufficient LL utilization test).

-- FAULT FINDINGS --------------------------------------------------
[CRITICAL] Watchdog timeout / reset at t=4.850s (cause=WDT, last_task=ctrl_loop)
[ERROR   ] PMIC brownout at t=2.377s (vbat=2.93V) ...
[INFO    ] 9 total CRC failures observed.
```

Plots produced by `report`: dispatch **timeline** (with fault markers), period
**jitter** histograms, and a period-vs-cycle **anomaly** scatter.

## Layout

```
fwlog/
  schema.py     Event dataclass + Severity/EventType enums (the shared model)
  generator.py  seeded RTOS log generator with fault injection
  parser.py     ordered-grammar parser, timestamp normalization
  analysis.py   period/jitter/exec stats, deadline misses, RM schedulability
  anomaly.py    rolling z-score and robust MAD outlier detectors
  faults.py     pluggable fault-signature rule engine
  viz.py        matplotlib plots (optional dependency)
  report.py     text report assembly
  cli.py        argparse CLI (generate / parse / analyze / report)
tests/          pytest suite incl. an end-to-end ground-truth test
docs/           TECHNICAL_WRITEUP.md — model, assumptions, and the math
```

## Tests

```bash
python3 -m pytest -q          # 21 tests, ~0.1s
```

The integration test generates a log with known injected faults and asserts the
analyzer recovers them (parse rate, watchdog reset, brown-out, per-task cycles).

## Extending it

* **New log format** -> append a regex to `_LINE_RES` in `parser.py`.
* **New fault signature** -> write a function decorated with `@rule` in
  `faults.py`; it's auto-registered.
* **New detector** -> add to `anomaly.py` and expose it via `detect(method=...)`.

See `docs/TECHNICAL_WRITEUP.md` for the real-time model, the schedulability
math, and why MAD is preferred over z-score here.
