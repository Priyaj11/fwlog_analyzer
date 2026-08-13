from fwlog.parser import parse_lines, ParseStats, _parse_timestamp
from fwlog.schema import EventType, Severity


def test_timestamp_formats():
    assert abs(_parse_timestamp("[  0.001234]") - 0.001234) < 1e-9
    assert abs(_parse_timestamp("2500 ms") - 2.5) < 1e-9
    iso = _parse_timestamp("2026-08-05T12:00:01.000Z")
    assert iso is not None and iso > 0


def test_timestamps_normalized_to_zero():
    lines = [
        "[  10.000000] INFO  sched: task=a prio=1 dispatch cycle=0",
        "[  10.010000] INFO  sched: task=a prio=1 dispatch cycle=1",
    ]
    events = list(parse_lines(lines))
    assert events[0].t == 0.0
    assert abs(events[1].t - 0.010) < 1e-9


def test_classifies_event_types():
    lines = [
        "[0.0] INFO  sched: task=x prio=2 dispatch cycle=0",
        "[0.1] INFO  sched: task=x prio=2 complete exec_us=1200",
        "[0.2] ERROR wdt: WATCHDOG TIMEOUT reset_cause=WDT",
        "[0.3] ERROR pmic: brownout detected vbat=2.90V",
        "300 ms INFO net: frame seq=5 crc=FAIL",
    ]
    ev = list(parse_lines(lines))
    types = [e.etype for e in ev]
    assert EventType.DISPATCH in types
    assert EventType.COMPLETE in types
    assert EventType.WATCHDOG_RESET in types
    assert EventType.BROWNOUT in types
    assert EventType.CRC_FAIL in types


def test_key_value_extraction():
    ev = list(parse_lines(["[0.0] INFO sched: task=ctrl prio=2 complete exec_us=2500"]))
    assert ev[0].task == "ctrl"
    assert ev[0].get_float("exec_us") == 2500.0
    assert ev[0].fields["prio"] == "2"


def test_unparseable_counted_not_raised():
    stats = ParseStats()
    lines = [
        "[0.0] INFO sched: task=a prio=1 dispatch cycle=0",
        ">>> raw dump 0xDEADBEEF garbage",
        "",  # blank ignored, not counted
    ]
    ev = list(parse_lines(lines, stats))
    assert len(ev) == 1
    assert stats.total == 2
    assert stats.parsed == 1
    assert stats.unparsed == 1


def test_severity_parsing():
    assert Severity.parse("E") == Severity.ERROR
    assert Severity.parse("warn") == Severity.WARN
    assert Severity.parse("nonsense") == Severity.INFO
