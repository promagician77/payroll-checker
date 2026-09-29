"""Check thresholds. Change them here, in settings.json, or on the page."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class Settings:
    # Overtime above either limit is flagged as "unusually high".
    overtime_max_hours: float = 40.0
    overtime_max_pct_of_contracted: float = 25.0
    # Adult (20+) national minimum wage in Ireland from 1 January 2026.
    # Lower youth rates exist, so this is a warning, not an error.
    minimum_hourly_rate: float = 14.15
    # Organisation of Working Time Act: 48 hours a week on average.
    max_avg_weekly_hours: float = 48.0
    weeks_per_month: float = 4.33
    # Is overtime already part of worked hours, or on top of it?
    worked_includes_overtime: bool = True
    # Blank overtime / sick / holiday / bonus is read as 0 instead of "missing".
    blank_optional_means_zero: bool = True
    # Hours beyond contract that aren't recorded as overtime, before we flag it.
    unrecorded_hours_tolerance: float = 1.0

    @classmethod
    def load(cls, overrides: dict | None = None, path: Path | None = None) -> "Settings":
        data: dict = {}
        path = path or Path(__file__).resolve().parent.parent / "settings.json"
        if path.exists():
            data.update(json.loads(path.read_text(encoding="utf-8")))
        if overrides:
            data.update(overrides)
        known = {f.name: f.type for f in fields(cls)}
        clean = {}
        for k, v in data.items():
            if k not in known:
                continue
            clean[k] = bool(v) if known[k] == "bool" else float(v)
        return cls(**clean)

    def as_dict(self) -> dict:
        return asdict(self)
