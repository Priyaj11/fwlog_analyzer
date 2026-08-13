from fwlog.parser import parse_lines
from fwlog.analysis import analyze_tasks, schedulability, _infer_nominal_period


def _periodic_lines(task, period_ms, n, exec_us=1000, start=0.0):
    out = []
    p = period_ms / 1000.0
    for k in range(n):
        t = start + k * p
        out.append(f"[{t:.6f}] INFO sched: task={task} prio=1 dispatch cycle={k}")
        out.append(f"[{t + exec_us/1e6:.6f}] INFO sched: task={task} prio=1 "
                   f"complete exec_us={exec_us}")
    return out


def test_period_and_jitter_recovered():
    ev = list(parse_lines(_periodic_lines("a", period_ms=10, n=50)))
    stats = analyze_tasks(ev)
    a = stats["a"]
    assert a.n_cycles == 50
    assert abs(a.nominal_period_s - 0.010) < 1e-4
    assert a.period_jitter_s < 1e-6          # perfectly periodic -> ~0 jitter


def test_nominal_period_is_robust_to_outlier():
    # one huge gap should not move the median-based nominal estimate
    periods = [0.010] * 20 + [0.5]
    assert abs(_infer_nominal_period(periods) - 0.010) < 1e-9


def test_deadline_miss_detected():
    import re
    lines = _periodic_lines("a", period_ms=10, n=20)
    # drop cycles 10 and 11 entirely -> a ~30ms gap between dispatches 9 and 12
    skip = re.compile(r"cycle=1[01]\b")
    lines = [l for l in lines if not skip.search(l)]
    ev = list(parse_lines(lines))
    stats = analyze_tasks(ev)
    assert stats["a"].deadline_misses >= 1


def test_utilization_and_schedulability():
    # task a: 1000us every 10ms -> U=0.1 ; task b: 2000us every 20ms -> U=0.1
    ev = list(parse_lines(
        _periodic_lines("a", 10, 100, exec_us=1000)
        + _periodic_lines("b", 20, 50, exec_us=2000)))
    stats = analyze_tasks(ev)
    assert abs(stats["a"].utilization - 0.1) < 0.02
    sched = schedulability(stats)
    assert sched.total_utilization < sched.ll_bound
    assert sched.schedulable_ll
    assert not sched.overloaded
