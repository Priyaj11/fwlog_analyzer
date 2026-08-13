"""fwlog - Firmware/RTOS log analyzer & timing-anomaly detector."""
from .schema import Event, EventType, Severity
from .parser import parse_file, parse_lines, ParseStats
from .analysis import analyze_tasks, schedulability, TaskStats
from .anomaly import detect, Anomaly
from .faults import run_rules, Finding

__version__ = "0.1.0"

__all__ = [
    "Event", "EventType", "Severity",
    "parse_file", "parse_lines", "ParseStats",
    "analyze_tasks", "schedulability", "TaskStats",
    "detect", "Anomaly",
    "run_rules", "Finding",
]
