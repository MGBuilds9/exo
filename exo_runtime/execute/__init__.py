"""exo execute — close the action loop.

Reads solve plans, runs commands with consent, parses output, drives
toward resolution or a ticket-worthy summary.
"""
from .safety import classify_command, SafetyClass
from .runner import run_command, CommandResult
from .parser import parse_output, ObservedSignal
from .session import ExecuteSession, SessionStep

__all__ = [
    "classify_command", "SafetyClass",
    "run_command", "CommandResult",
    "parse_output", "ObservedSignal",
    "ExecuteSession", "SessionStep",
]
