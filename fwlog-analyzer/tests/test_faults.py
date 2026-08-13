from fwlog.parser import parse_lines
from fwlog.faults import run_rules


def test_watchdog_reset_finding():
    ev = list(parse_lines([
        "[0.0] INFO sched: task=a prio=1 dispatch cycle=0",
        "[0.5] ERROR wdt: WATCHDOG TIMEOUT reset_cause=WDT last_task=a",
    ]))
    findings = run_rules(ev)
    assert any(f.rule == "watchdog_reset" and f.severity == "critical"
               for f in findings)


def test_brownout_finding():
    ev = list(parse_lines(["[1.0] ERROR pmic: brownout detected vbat=2.85V thresh=3.00V"]))
    findings = run_rules(ev)
    b = [f for f in findings if f.rule == "brownout"]
    assert b and "2.85" in b[0].message


def test_crc_burst_vs_isolated():
    # 3 CRC fails within 0.5s -> a burst finding
    burst = list(parse_lines([
        "0 ms INFO net: frame seq=0 crc=FAIL",
        "100 ms INFO net: frame seq=1 crc=FAIL",
        "200 ms INFO net: frame seq=2 crc=FAIL",
    ]))
    findings = run_rules(burst)
    assert any(f.rule == "crc_burst" for f in findings)

    # isolated fails far apart -> no burst
    isolated = list(parse_lines([
        "0 ms INFO net: frame seq=0 crc=FAIL",
        "5000 ms INFO net: frame seq=1 crc=FAIL",
    ]))
    assert not any(f.rule == "crc_burst" for f in run_rules(isolated))


def test_task_starvation():
    lines = []
    # normal 10ms cadence then a long 100ms gap
    for k in range(10):
        lines.append(f"[{k*0.01:.6f}] INFO sched: task=low prio=1 dispatch cycle={k}")
    lines.append(f"[{0.09 + 0.1:.6f}] INFO sched: task=low prio=1 dispatch cycle=10")
    findings = run_rules(list(parse_lines(lines)))
    assert any(f.rule == "task_starvation" for f in findings)
