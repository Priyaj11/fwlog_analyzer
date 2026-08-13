"""End-to-end: generate a log with known faults, then confirm the analyzer
recovers them. This is the strongest test - it exercises generator -> parser ->
analysis -> fault rules as a pipeline against ground truth.
"""
from fwlog.generator import generate
from fwlog.parser import parse_file, ParseStats
from fwlog.analysis import analyze_tasks
from fwlog.faults import run_rules


def test_pipeline_recovers_injected_faults(tmp_path):
    log = tmp_path / "device.log"
    truth = generate(str(log), duration_s=6.0, seed=7, inject=True)

    stats = ParseStats()
    events = parse_file(str(log), stats)

    # parser should handle the vast majority of the (messy) log
    assert stats.parse_rate > 0.95

    findings = run_rules(events)
    rules = [f.rule for f in findings]

    # watchdog reset was injected exactly once -> must be found
    assert truth["watchdog_resets"] == 1
    assert rules.count("watchdog_reset") == 1

    # brownouts injected -> at least one brownout finding
    assert truth["brownouts"] >= 1
    assert "brownout" in rules

    # task stats populated for all three default tasks
    ts = analyze_tasks(events)
    assert {"sensor_poll", "ctrl_loop", "telemetry"} <= set(ts)
    assert all(t.n_cycles > 0 for t in ts.values())


def test_clean_log_has_no_critical_faults(tmp_path):
    log = tmp_path / "clean.log"
    generate(str(log), duration_s=4.0, seed=1, inject=False)
    events = parse_file(str(log))
    findings = run_rules(events)
    assert not any(f.severity == "critical" for f in findings)
