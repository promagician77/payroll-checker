"""Reading payroll CSVs the way they really arrive: from Excel, from payroll systems,
with BOMs, semicolons, euro signs, and the odd stray comma.

Nothing here uses pandas on purpose: every original value is kept as the exact text
from the file, so the issues CSV shows employee IDs like 00123 unchanged."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

COLUMNS = {
    # canonical name: (label shown to the user, accepted header spellings)
    "employee_id": ("Employee ID", ["employeeid", "empid", "empno", "empnumber", "empcode", "employeecode",
                                    "employeeno", "employeenumber", "employeeref", "staffcode",
                                    "staffid", "staffno", "staffnumber", "payrollno", "payrollnumber", "id"]),
    "employee_name": ("Name", ["name", "employeename", "fullname", "staffname"]),
    "store": ("Store", ["store", "storename", "storeid", "location", "branch", "site", "shop"]),
    "contracted_hours": ("Contracted hours", ["contractedhours", "contracthours", "contracted", "scheduledhours"]),
    "worked_hours": ("Worked hours", ["workedhours", "hoursworked", "actualhours", "totalhours", "worked"]),
    "overtime_hours": ("Overtime hours", ["overtime", "overtimehours", "othours", "ot"]),
    "sick_hours": ("Sick hours", ["sickhours", "sick", "sickleave", "sickleavehours"]),
    "vacation_hours": ("Holiday hours", ["vacationhours", "vacation", "holidayhours", "holiday", "holidays",
                                        "annualleave", "annualleavehours", "leavehours"]),
    "hourly_rate": ("Hourly rate", ["hourlyrate", "rate", "payrate", "rateperhour", "hourlypay"]),
    "bonus": ("Bonus", ["bonus", "bonuses", "bonusamount"]),
}
EXPECTED = ["employee_id", "store", "contracted_hours", "worked_hours", "overtime_hours",
            "sick_hours", "vacation_hours", "hourly_rate", "bonus"]
DELIMITER_NAMES = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}


def norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


@dataclass
class ParsedFile:
    encoding: str = "utf-8"
    delimiter: str = ","
    header: list[str] = field(default_factory=list)
    rows: list[tuple[int, list[str]]] = field(default_factory=list)  # (row number in the file, values)
    column_index: dict[str, int] = field(default_factory=dict)
    missing_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    blank_rows: int = 0
    file_issues: list[str] = field(default_factory=list)

    @property
    def delimiter_name(self) -> str:
        return DELIMITER_NAMES.get(self.delimiter, repr(self.delimiter))


def decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace"), "UTF-8 (with BOM)"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "UTF-16"  # Excel's "Unicode Text" export
    try:
        return raw.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError:
        # Older Excel on Windows saves CSV as Windows-1252; fadas survive this way.
        return raw.decode("cp1252", errors="replace"), "Windows-1252"


def sniff_delimiter(text: str) -> str:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    counts = {d: first.count(d) for d in DELIMITER_NAMES}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def read_payroll(raw: bytes) -> ParsedFile:
    pf = ParsedFile()
    if not raw.strip():
        pf.file_issues.append("The file is empty.")
        return pf
    text, pf.encoding = decode(raw)
    pf.delimiter = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=pf.delimiter)
    try:
        all_rows = list(reader)
    except csv.Error as e:
        pf.file_issues.append(f"The file couldn't be read as CSV ({e}).")
        return pf

    header_at = next((i for i, r in enumerate(all_rows) if any(c.strip() for c in r)), None)
    if header_at is None:
        pf.file_issues.append("The file has no header row.")
        return pf
    pf.header = [h.strip() for h in all_rows[header_at]]
    while pf.header and pf.header[-1] == "":  # trailing ;;; from Excel
        pf.header.pop()

    seen: dict[str, int] = {}
    for i, h in enumerate(pf.header):
        key = norm(h)
        for canon, (_, aliases) in COLUMNS.items():
            if key in aliases and canon not in pf.column_index:
                pf.column_index[canon] = i
                break
        else:
            if h:
                pf.extra_columns.append(h)
        if key and key in seen:
            pf.file_issues.append(f'Column "{h}" appears twice in the header (columns {seen[key] + 1} and {i + 1}).')
        seen.setdefault(key, i)
    pf.missing_columns = [COLUMNS[c][0] for c in EXPECTED if c not in pf.column_index]
    if pf.missing_columns:
        pf.file_issues.append("Columns not found: " + ", ".join(pf.missing_columns)
                              + ". Checks that need them were skipped.")

    width = len(pf.header)
    for offset, values in enumerate(all_rows[header_at + 1:], start=header_at + 2):
        if not any(v.strip() for v in values):
            pf.blank_rows += 1
            continue
        while len(values) > width and values[-1] == "":
            values = values[:-1]
        pf.rows.append((offset, values))
    return pf


_PLAIN = re.compile(r"-?\d+(\.\d+)?")
_THOUSANDS = re.compile(r"-?\d{1,3}(,\d{3})+(\.\d+)?")
_EURO_DECIMAL = re.compile(r"-?\d{1,3}(\.\d{3})*,\d+|-?\d+,\d+")


def parse_number(raw: str, delimiter: str) -> tuple[float | None, str | None]:
    """Returns (value, problem). Blank gives (None, 'blank')."""
    s = raw.strip().replace("\u00a0", "").replace(" ", "").replace("€", "").replace("EUR", "")
    if s == "":
        return None, "blank"
    negative = s.startswith("(") and s.endswith(")")  # accounting style (25.00)
    if negative:
        s = s[1:-1]
    if _PLAIN.fullmatch(s):
        v = float(s)
    elif _THOUSANDS.fullmatch(s):
        v = float(s.replace(",", ""))
    elif _EURO_DECIMAL.fullmatch(s) and delimiter == ";":
        # Semicolon files come from European Excel, where the comma is the decimal mark.
        v = float(s.replace(".", "").replace(",", "."))
    elif _EURO_DECIMAL.fullmatch(s):
        return None, f"uses a comma as the decimal mark ('{raw.strip()}'), so it can't be read safely"
    else:
        return None, f"is not a number ('{raw.strip()}')"
    return (-v if negative else v), None


def write_issues_csv(pf: ParsedFile, flagged: list[tuple[int, list[str], str, str]]) -> str:
    """Original header and values, untouched, plus three columns at the end.
    Saved with a BOM so Excel shows fadas (Seán, Siobhán) correctly."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=pf.delimiter, lineterminator="\r\n")
    w.writerow(pf.header + ["Severity", "Issue reason", "Source row"])
    width = len(pf.header)
    for row_no, values, severity, reason in flagged:
        # Keep columns lined up: short rows are padded, extra values are listed in the reason.
        fitted = (values + [""] * width)[:width]
        w.writerow(fitted + [severity, reason, row_no])
    return "\ufeff" + buf.getvalue()
