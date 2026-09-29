"""The checks. Each one reads one row and returns zero or more issues.
Errors mean the row is wrong. Warnings mean it's worth a human look."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .csvio import COLUMNS, ParsedFile, parse_number, read_payroll, write_issues_csv
from .settings import Settings

REQUIRED = ["employee_id", "store", "contracted_hours", "worked_hours", "hourly_rate"]
OPTIONAL_NUMBERS = ["overtime_hours", "sick_hours", "vacation_hours", "bonus"]
HOURS = ["contracted_hours", "worked_hours", "overtime_hours", "sick_hours", "vacation_hours"]
NUMBERS = HOURS + ["hourly_rate", "bonus"]
HOURS_IN_A_MONTH = 31 * 24  # 744

CHECK_NAMES = {
    "format": "Row format",
    "missing": "Missing values",
    "not_number": "Not a number",
    "duplicate_id": "Duplicate employee ID",
    "negative": "Negative numbers",
    "impossible": "Impossible hours",
    "high_overtime": "Unusually high overtime",
    "overtime_vs_worked": "Overtime vs worked hours",
    "unrecorded_hours": "Hours beyond contract",
    "working_time": "Above 48-hour average week",
    "minimum_wage": "Below minimum wage",
    "no_hours": "No hours at all",
    "totals_row": "Totals row",
}


@dataclass
class Issue:
    check: str
    severity: str  # "error" or "warning"
    message: str


@dataclass
class RowResult:
    row: int
    values: list[str]
    employee_id: str
    store: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def severity(self) -> str:
        if any(i.severity == "error" for i in self.issues):
            return "error"
        return "warning" if self.issues else "ok"


def fmt(v: float) -> str:
    return f"{v:g}"


def check_row(pf: ParsedFile, row_no: int, values: list[str], s: Settings) -> RowResult:
    idx = pf.column_index
    get = lambda c: values[idx[c]].strip() if c in idx and idx[c] < len(values) else ""
    label = lambda c: COLUMNS[c][0]
    r = RowResult(row_no, values, get("employee_id"), get("store"))
    add = lambda check, sev, msg: r.issues.append(Issue(check, sev, msg))

    width = len(pf.header)
    if len(values) != width:
        extra = [v for v in values[width:] if v.strip()]
        msg = f"Row has {len(values)} values but the header has {width}"
        msg += f" (extra: {', '.join(extra)})" if extra else " - a stray delimiter or a missing value"
        add("format", "error", msg + ". Other checks skipped for this row.")
        return r

    first_text = " ".join(v.strip().lower() for v in values[:3])
    if not r.employee_id and ("total" in first_text):
        add("totals_row", "warning", "Looks like a totals row, not an employee.")
        return r

    nums: dict[str, float | None] = {}
    for c in NUMBERS:
        if c not in idx:
            continue
        v, problem = parse_number(get(c), pf.delimiter)
        if problem == "blank":
            if c in OPTIONAL_NUMBERS and s.blank_optional_means_zero:
                v = 0.0
            elif c in REQUIRED:
                add("missing", "error", f"Missing {label(c).lower()}")
            nums[c] = v
        elif problem:
            add("not_number", "error", f"{label(c)} {problem}")
            nums[c] = None
        else:
            nums[c] = v
    for c in ("employee_id", "store"):
        if c in idx and not get(c):
            add("missing", "error", f"Missing {label(c).lower()}")

    for c in HOURS + ["hourly_rate"]:
        if nums.get(c) is not None and nums[c] < 0:
            add("negative", "error", f"Negative {label(c).lower()} ({fmt(nums[c])})")
    if nums.get("bonus") is not None and nums["bonus"] < 0:
        add("negative", "warning", f"Negative bonus ({fmt(nums['bonus'])}) - a correction or clawback?")

    for c in HOURS:
        if nums.get(c) is not None and nums[c] > HOURS_IN_A_MONTH:
            add("impossible", "error", f"{label(c)} ({fmt(nums[c])}) is more than the hours in a month ({HOURS_IN_A_MONTH})")

    ot, worked, contracted = nums.get("overtime_hours"), nums.get("worked_hours"), nums.get("contracted_hours")
    if ot is not None and ot > 0:
        reasons = []
        if ot > s.overtime_max_hours:
            reasons.append(f"above {fmt(s.overtime_max_hours)} h")
        if contracted and contracted > 0 and ot / contracted * 100 > s.overtime_max_pct_of_contracted:
            reasons.append(f"{ot / contracted * 100:.0f}% of contracted hours")
        if reasons:
            add("high_overtime", "warning", f"High overtime: {fmt(ot)} h ({', '.join(reasons)})")

    if s.worked_includes_overtime and ot is not None and worked is not None and ot > worked and worked >= 0:
        add("overtime_vs_worked", "error", f"Overtime ({fmt(ot)} h) is more than total worked hours ({fmt(worked)} h)")

    if worked is not None and contracted is not None and worked > contracted:
        recorded_ot = (ot or 0) if s.worked_includes_overtime else 0
        unrecorded = worked - contracted - recorded_ot
        if unrecorded > s.unrecorded_hours_tolerance:
            add("unrecorded_hours", "warning",
                f"Worked {fmt(worked)} h, {fmt(round(worked - contracted, 2))} over contract, "
                + (f"but only {fmt(ot)} h recorded as overtime" if ot else "but no overtime recorded"))

    if worked is not None and worked >= 0:
        total = worked + (0 if s.worked_includes_overtime else (ot or 0))
        weekly = total / s.weeks_per_month
        if weekly > s.max_avg_weekly_hours:
            add("working_time", "warning",
                f"About {weekly:.0f} h a week this month, above the {fmt(s.max_avg_weekly_hours)} h average "
                "in the Working Time Act (it's averaged over months, so check recent months too)")

    rate = nums.get("hourly_rate")
    if rate is not None and 0 < rate < s.minimum_hourly_rate:
        add("minimum_wage", "warning",
            f"€{rate:.2f}/h is below the adult minimum wage (€{s.minimum_hourly_rate:.2f}) - fine only if a youth rate applies")

    if all(nums.get(c) == 0 for c in ("worked_hours", "sick_hours", "vacation_hours") if c in idx) \
            and "worked_hours" in idx:
        add("no_hours", "warning", "No worked, sick, or holiday hours this month - a leaver or a missing timesheet?")
    return r


def validate(raw: bytes, settings: Settings | None = None) -> dict:
    s = settings or Settings()
    pf = read_payroll(raw)
    results = [check_row(pf, n, v, s) for n, v in pf.rows]

    # Duplicates need the whole file, so they're checked after the row pass.
    by_id: dict[str, list[RowResult]] = defaultdict(list)
    for r in results:
        if r.employee_id and not any(i.check in ("format", "totals_row") for i in r.issues):
            by_id[r.employee_id.strip().upper()].append(r)
    for rows in by_id.values():
        if len(rows) > 1:
            for r in rows:
                others = ", ".join(str(o.row) for o in rows if o is not r)
                r.issues.append(Issue("duplicate_id", "error",
                                      f"Employee ID {r.employee_id} also appears on row {others}"))

    flagged = [r for r in results if r.issues]
    counts = defaultdict(int)
    for r in flagged:
        for c in {i.check for i in r.issues}:
            counts[c] += 1
    stores: dict[str, dict] = defaultdict(lambda: {"rows": 0, "issues": 0})
    for r in results:
        if any(i.check == "totals_row" for i in r.issues):
            continue
        key = r.store or "(no store)"
        stores[key]["rows"] += 1
        stores[key]["issues"] += 1 if r.issues else 0

    issues_csv = write_issues_csv(pf, [
        (r.row, r.values, r.severity.capitalize(), " | ".join(i.message for i in r.issues)) for r in flagged
    ]) if pf.header else ""

    return {
        "file": {
            "encoding": pf.encoding,
            "delimiter": pf.delimiter_name,
            "columns_found": {COLUMNS[c][0]: pf.header[i] for c, i in pf.column_index.items()},
            "columns_missing": pf.missing_columns,
            "columns_extra": pf.extra_columns,
            "blank_rows_skipped": pf.blank_rows,
            "problems": pf.file_issues,
        },
        "summary": {
            "total_rows": len(results),
            "ok": sum(1 for r in results if not r.issues),
            "with_issues": len(flagged),
            "errors": sum(1 for r in flagged if r.severity == "error"),
            "warnings": sum(1 for r in flagged if r.severity == "warning"),
        },
        "checks": [{"check": k, "name": CHECK_NAMES[k], "rows": counts[k]} for k in CHECK_NAMES if counts.get(k)],
        "stores": [{"store": k, **v} for k, v in sorted(stores.items())],
        "rows": [{
            "row": r.row, "employee_id": r.employee_id, "store": r.store, "severity": r.severity,
            "issues": [{"check": i.check, "severity": i.severity, "message": i.message} for i in r.issues],
        } for r in flagged],
        "issues_csv": issues_csv,
        "settings": s.as_dict(),
    }

