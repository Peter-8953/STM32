"""Return-value dataclasses for DS3231 methods.

Using dataclasses instead of bare tuples means callers read fields by
name (e.g. ``reading.temperature``) instead of by position
(``reading[0]``), and never need an ``isinstance`` check to figure out
what came back.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TempReading:
    """Result of ``DS3231.temperature``."""
    temperature: float    # Celsius
    read_at: datetime     # Time reported by the DS3231 itself (UTC)
    seq: int              # SEQ of the frame this reading came from


@dataclass
class TimeReading:
    """Result of ``DS3231.datetime``."""
    datetime: datetime    # Time reported by the DS3231 (UTC)
    seq: int              # SEQ of the frame this reading came from


@dataclass
class SyncResult:
    """Result of ``DS3231.sync_from_pc()``."""
    seq: int              # SEQ of the ACK frame
