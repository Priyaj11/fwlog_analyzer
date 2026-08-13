"""Core data model for parsed firmware/RTOS log events.

Everything downstream (analysis, anomaly detection, fault rules) operates on
the normalized `Event` objects defined here, not on raw text. Keeping a single
typed schema is what lets the parser accept many messy line formats while the
rest of the tool stays simple.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Severity(Enum):
    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40
    CRITICAL = 50

    @classmethod
    def parse(cls, token: str) -> "Severity":
        t = token.strip().upper()
        table = {
            "D": cls.DEBUG, "DBG": cls.DEBUG, "DEBUG": cls.DEBUG,
            "I": cls.INFO, "INF": cls.INFO, "INFO": cls.INFO,
            "W": cls.WARN, "WRN": cls.WARN, "WARN": cls.WARN, "WARNING": cls.WARN,
            "E": cls.ERROR, "ERR": cls.ERROR, "ERROR": cls.ERROR,
            "C": cls.CRITICAL, "CRIT": cls.CRITICAL, "CRITICAL": cls.CRITICAL,
            "F": cls.CRITICAL, "FATAL": cls.CRITICAL,
        }
        return table.get(t, cls.INFO)


class EventType(Enum):
    """Semantic category assigned by the parser based on subsystem + keywords."""
    DISPATCH = "dispatch"          # RTOS scheduler dispatched a task
    COMPLETE = "complete"          # task finished a cycle
    WATCHDOG_FEED = "wdt_feed"     # watchdog kicked / fed
    WATCHDOG_RESET = "wdt_reset"   # watchdog expired -> reset
    BROWNOUT = "brownout"          # PMIC undervoltage
    CRC_FAIL = "crc_fail"          # comm frame integrity error
    BOOT = "boot"                  # boot / reset banner
    LOG = "log"                    # generic log line
    UNKNOWN = "unknown"


@dataclass
class Event:
    """A single normalized log event.

    Attributes
    ----------
    t : float
        Monotonic timestamp in seconds, normalized so the log starts at ~0.
    severity : Severity
    etype : EventType
    subsystem : str
        Emitting module, e.g. "sched", "wdt", "pmic", "net".
    task : Optional[str]
        Task name for scheduler events.
    fields : dict
        Any extra key=value pairs pulled from the line (prio, exec_us, vbat...).
    raw : str
        Original line, kept for traceability in reports.
    line_no : int
    """
    t: float
    severity: Severity
    etype: EventType
    subsystem: str
    raw: str
    line_no: int
    task: Optional[str] = None
    fields: dict[str, Any] = field(default_factory=dict)

    def get_float(self, key: str, default: Optional[float] = None) -> Optional[float]:
        """Return a numeric field, tolerating unit suffixes like '2.85V' or '1200us'."""
        v = self.fields.get(key)
        if v is None:
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            import re
            m = re.match(r"[-+]?\d*\.?\d+", str(v))  # leading numeric part
            return float(m.group()) if m else default
