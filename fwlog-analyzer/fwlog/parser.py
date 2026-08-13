"""Grammar-based log parser.

The parser is a small ordered list of (regex, handler) "grammars". Each raw
line is tried against every grammar until one matches; the handler turns the
capture groups into a normalized :class:`Event`. Timestamps arrive in three
formats (seconds in brackets, milliseconds, ISO-8601) and are all normalized to
monotonic seconds relative to the first timestamp seen.

This design is deliberate: adding support for a new firmware's line format means
appending one grammar, not touching downstream analysis.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional

from .schema import Event, EventType, Severity

# --- timestamp helpers ------------------------------------------------------

_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?")


def _parse_timestamp(tok: str) -> Optional[float]:
    """Return an *absolute* seconds value; normalization to t0 happens later."""
    tok = tok.strip()
    if _ISO_RE.fullmatch(tok):
        s = tok.rstrip("Z")
        dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return dt.timestamp()
    m = re.fullmatch(r"\[?\s*([0-9]+\.[0-9]+)\s*\]?", tok)      # seconds
    if m:
        return float(m.group(1))
    m = re.fullmatch(r"([0-9]+)\s*ms", tok)                       # milliseconds
    if m:
        return float(m.group(1)) / 1000.0
    return None


def _kv(rest: str) -> dict[str, str]:
    """Pull all key=value tokens out of the free-form remainder of a line."""
    return dict(re.findall(r"(\w+)=([^\s]+)", rest))


# --- grammar table ----------------------------------------------------------
# Each grammar is a compiled regex exposing named groups ts/sev/sub/rest.

_LINE_RES = [
    # [  0.001234] INFO  sched: task=... rest
    re.compile(r"^(?P<ts>\[[^\]]+\])\s+(?P<sev>\w+)\s+(?P<sub>\w+):\s*(?P<rest>.*)$"),
    # 1234 ms  INFO net: rest
    re.compile(r"^(?P<ts>[0-9]+\s*ms)\s+(?P<sev>\w+)\s+(?P<sub>\w+):\s*(?P<rest>.*)$"),
    # 2026-08-05T12:00:01.123Z INFO net: rest
    re.compile(r"^(?P<ts>\S+Z)\s+(?P<sev>\w+)\s+(?P<sub>\w+):\s*(?P<rest>.*)$"),
]


def _classify(subsystem: str, rest: str, sev: Severity) -> tuple[EventType, Optional[str]]:
    r = rest.lower()
    task = None
    kv = _kv(rest)
    if subsystem == "sched":
        task = kv.get("task")
        if "dispatch" in r:
            return EventType.DISPATCH, task
        if "complete" in r:
            return EventType.COMPLETE, task
    if subsystem == "wdt":
        if "timeout" in r or "reset" in r:
            return EventType.WATCHDOG_RESET, None
        return EventType.WATCHDOG_FEED, None
    if subsystem == "pmic" and "brownout" in r:
        return EventType.BROWNOUT, None
    if subsystem == "net" and "crc=fail" in r:
        return EventType.CRC_FAIL, None
    if subsystem == "boot" or "reset" in r:
        return EventType.BOOT, None
    return EventType.LOG, task


class ParseStats:
    def __init__(self) -> None:
        self.total = 0
        self.parsed = 0
        self.unparsed = 0

    @property
    def parse_rate(self) -> float:
        return self.parsed / self.total if self.total else 0.0


def parse_lines(lines: Iterable[str], stats: Optional[ParseStats] = None) -> Iterator[Event]:
    """Yield normalized Events from raw log lines.

    Timestamps are normalized so the first successfully parsed event is t=0.
    Unparseable lines are counted (via `stats`) and skipped.
    """
    stats = stats if stats is not None else ParseStats()
    t0: Optional[float] = None
    for i, line in enumerate(lines):
        line = line.rstrip("\n")
        if not line.strip():
            continue
        stats.total += 1
        for rx in _LINE_RES:
            m = rx.match(line)
            if not m:
                continue
            ts_abs = _parse_timestamp(m.group("ts"))
            if ts_abs is None:
                continue
            if t0 is None:
                t0 = ts_abs
            sev = Severity.parse(m.group("sev"))
            sub = m.group("sub")
            rest = m.group("rest")
            etype, task = _classify(sub, rest, sev)
            stats.parsed += 1
            yield Event(
                t=ts_abs - t0,
                severity=sev,
                etype=etype,
                subsystem=sub,
                task=task,
                fields=_kv(rest),
                raw=line,
                line_no=i + 1,
            )
            break
        else:
            stats.unparsed += 1


def parse_file(path: str, stats: Optional[ParseStats] = None) -> list[Event]:
    with open(path) as fh:
        events = list(parse_lines(fh, stats))
    # ISO/ms/seconds can interleave; guarantee monotonic order for analysis.
    events.sort(key=lambda e: e.t)
    return events
