# Technical Writeup — fwlog

This document explains the model, assumptions, and mathematics behind the
analyzer. It is written for a reader with an embedded / real-time systems
background (i.e. the level of a graduate ECE course on real-time systems).

## 1. Problem

Embedded systems emit large, unstructured serial (UART) logs. Timing bugs —
missed deadlines, task jitter, watchdog resets, priority inversion, supply
brown-outs, link-integrity errors — are painful to find by eye because the
relevant events are sparse and interleaved across subsystems. The goal of
`fwlog` is to turn that raw text into quantitative timing metrics and an
automatic list of suspected faults.

## 2. System model

We assume a fixed-priority preemptive RTOS running a set of **periodic tasks**
`tau_i`, each characterized by a period `T_i`, a worst-case execution time
`C_i`, and (in the implicit-deadline model) a relative deadline `D_i = T_i`. The
scheduler emits a `dispatch` event when a job is released/started and a
`complete` event carrying the measured execution time `exec_us` when it
finishes. This is the standard Liu & Layland periodic task model.

The parser reconstructs, per task, the sequence of dispatch timestamps
`{t_0, t_1, ...}` and execution times `{e_0, e_1, ...}`.

## 3. Timing metrics

**Measured period** — the inter-dispatch intervals `p_k = t_{k+1} - t_k`.

**Nominal period estimate** — we use the *median* of `{p_k}` rather than the
mean. A dropped or delayed cycle produces one large `p_k`; the mean is dragged
toward it, but the median (breakdown point 50%) is not. This matters because the
nominal period is the reference against which we later judge deadline misses, so
it must be robust.

**Period jitter** — the population standard deviation of `{p_k}`, reported in
microseconds. This is release jitter: how much the actual release times wander
around the ideal periodic grid.

**Execution statistics** — mean, 95th percentile, and max of `{e_k}`. The p95 is
a more honest "how long does this usually take at worst" than the raw max, which
is a single outlier.

## 4. Deadline-miss detection

Under the implicit-deadline model a job of `tau_i` misses its deadline if its
**response time** `R_{i,k}` (release -> completion) exceeds `D_i = T_i`. We flag
a miss when either:

1. **Response-time overrun**: `e_k > T_i` (the job's own execution time exceeds
   its period). This is an unambiguous miss regardless of scheduling.
2. **Release slip**: `p_k > 1.5 * T_i`. A gap markedly larger than the nominal
   period means a release was skipped or badly delayed — the job did not run
   when it should have. The 1.5x factor is a tolerance that absorbs normal
   jitter while catching a genuine skipped cycle (which would be ~2x).

The two mechanisms are complementary: (1) catches jobs that run too long, (2)
catches jobs that were prevented from running (e.g. starved by a higher-priority
task).

## 5. Schedulability check (Liu & Layland)

Per-task utilization is `U_i = C_i / T_i`; here we estimate it empirically as
`U_i = sum(e_k) / W`, the total CPU time the task consumed over the observation
window `W`. Total utilization is `U = sum(U_i)`.

For `n` tasks under rate-monotonic priority assignment, Liu & Layland (1973)
give the **sufficient** utilization bound

```
U <= n * (2^(1/n) - 1)
```

which tends to `ln 2 ~= 0.693` as `n -> infinity`. The tool reports three
verdicts:

* `U <= bound` -> **schedulable** (the sufficient test passes).
* `bound < U <= 1` -> **inconclusive**: the LL test is sufficient, not necessary,
  so the set may still be schedulable — the correct next step is exact
  response-time analysis (RTA). The tool says so rather than guessing.
* `U > 1` -> **overloaded**: no priority assignment can meet all deadlines.

Being explicit that the LL test is only sufficient (not necessary) is the point:
a real analysis tool should not claim "unschedulable" when it only knows "beyond
the easy bound."

## 6. Statistical anomaly detection

Deadline logic (Section 4) tests against a *known model*. It will miss slow
drift or spikes that stay under the hard threshold but are still abnormal. So we
add a model-free detector on the timing series.

**Rolling z-score (baseline).** For point `x_i`, compute mean `mu` and std
`sigma` over a trailing window and flag if `|x_i - mu| / sigma >= 3`. Two
problems on embedded timing data: (a) it assumes normality, and (b) it suffers
**masking** — the very outliers we want to detect inflate `sigma`, shrinking
their own scores, so a cluster of spikes can hide itself.

**Rolling MAD (recommended).** Use the median and the Median Absolute Deviation:

```
MAD = median(|x_i - median(x)|)
robust_z = 0.6745 * (x_i - median) / MAD
```

The constant `0.6745` rescales MAD to be a consistent estimator of `sigma` for
Gaussian data (since the 0.75 quantile of the standard normal is ~0.6745).
Iglewicz & Hoaglin recommend a threshold of ~3.5. Because both the center and
scale estimators have a 50% breakdown point, a handful of spikes cannot mask
each other. This is why MAD is the default `--method`.

Degenerate case: if the trailing window is perfectly flat (`sigma = 0` or
`MAD = 0`), any departure is by definition an infinite-sigma deviation, so we
flag it rather than divide by zero. This is an edge case in synthetic data but
the correct behavior.

## 7. Fault-signature rules

A small rule engine (`faults.py`) scans the event stream for known failure
signatures; each rule is an independent, auto-registered function:

* **watchdog_reset** — a watchdog timeout event (critical); typically implies a
  task hung or an ISR ran too long.
* **brownout** — a PMIC undervoltage event; points at supply droop / decoupling.
* **crc_burst** — >= N CRC failures within a time window. Isolated CRC errors are
  normal on a noisy link; a *burst* indicates a real integrity problem (EMI, bad
  clocking, buffer overrun). We deliberately distinguish burst from background
  rate.
* **task_starvation** — a task not dispatched for >> its nominal period; the
  classic symptom of priority inversion.

## 8. Reproducible fault injection

Because real logs are proprietary and non-reproducible, `generator.py` models
the task set above and emits a UART-style log with faults injected under a
seeded RNG. It returns a ground-truth dict, which the integration test uses to
assert that the pipeline recovers the injected faults. The generator also emits
deliberately heterogeneous timestamp formats and a few un-parseable lines to
exercise the parser's fallback logic.

## 9. Limitations & possible extensions

* The empirical utilization is a lower bound on the true `U` if the observation
  window doesn't capture worst-case execution times.
* Deadline detection assumes implicit deadlines (`D = T`); constrained deadlines
  (`D < T`) would need the release/completion pairing tracked per job.
* A natural extension is exact **response-time analysis** (the fixed-point
  iteration `R_i = C_i + sum_{j in hp(i)} ceil(R_i / T_j) * C_j`) to resolve the
  "inconclusive" schedulability verdict.
* Anomaly detection currently runs per-series; a multivariate detector could
  correlate exec-time spikes with brown-out or starvation events.

## References

* C. L. Liu and J. W. Layland, "Scheduling Algorithms for Multiprogramming in a
  Hard-Real-Time Environment," *JACM*, 1973.
* B. Iglewicz and D. Hoaglin, *How to Detect and Handle Outliers*, ASQC, 1993
  (the modified z-score / MAD threshold).
* M. Joseph and P. Pandya, "Finding Response Times in a Real-Time System,"
  *The Computer Journal*, 1986 (response-time analysis).
