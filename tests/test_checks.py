"""Run with: pytest"""
import csv
import io
from pathlib import Path

from fastapi.testclient import TestClient

from app.csvio import parse_number, read_payroll
from app.main import app
from app.rules import validate
from app.settings import Settings

SAMPLES = Path(__file__).resolve().parent.parent / "web" / "sample"
HEADER = "Employee ID,Store,Contracted Hours,Worked Hours,Overtime Hours,Sick Hours,Holiday Hours,Hourly Rate,Bonus"


def run(*rows, header=HEADER, settings=None, encoding="utf-8"):
    return validate(("\r\n".join([header, *rows]) + "\r\n").encode(encoding), settings)


def messages(result):
    return [i["message"] for r in result["rows"] for i in r["issues"]]


def checks(result):
    return {i["check"] for r in result["rows"] for i in r["issues"]}


# ---------- reading files ----------

def test_clean_row_has_no_issues():
    d = run("001,Dublin,160,160,0,0,0,15.80,0")
    assert d["summary"] == {"total_rows": 1, "ok": 1, "with_issues": 0, "errors": 0, "warnings": 0}


def test_excel_bom_semicolons_and_comma_decimals():
    raw = "\ufeffEmp No;Branch;Contract Hours;Hours Worked;OT;Sick Leave;Annual Leave;Pay Rate;Bonus\r\n" \
          "001;Cork;162,5;162,5;0;0;7,5;16,10;1.250,00\r\n"
    d = validate(raw.encode("utf-8"))
    assert d["file"]["encoding"] == "UTF-8 (with BOM)"
    assert d["file"]["delimiter"] == "semicolon"
    assert d["file"]["columns_missing"] == []
    assert d["summary"]["ok"] == 1


def test_windows_1252_file_keeps_fadas():
    d = run("001,Dún Laoghaire,160,160,0,0,0,15.80,0", encoding="cp1252")
    assert d["file"]["encoding"] == "Windows-1252"
    assert d["stores"][0]["store"] == "Dún Laoghaire"


def test_header_spellings_are_recognised():
    pf = read_payroll(b"Staff No,Location,Contracted,Hours Worked,OT Hours,Sick,Holiday Hours,Pay Rate,Bonus\n1,a,1,1,0,0,0,15,0\n")
    assert pf.missing_columns == []


def test_missing_column_is_reported_not_crashed():
    d = run("001,Dublin,160,160,0,0,0,0", header=HEADER.replace(",Hourly Rate", ""))
    assert "Hourly rate" in d["file"]["columns_missing"]
    assert any("Columns not found" in p for p in d["file"]["problems"])


def test_blank_rows_are_skipped_and_counted():
    d = run("001,Dublin,160,160,0,0,0,15.80,0", ",,,,,,,,", "")
    assert d["summary"]["total_rows"] == 1
    assert d["file"]["blank_rows_skipped"] == 2


def test_empty_file():
    d = validate(b"   ")
    assert d["file"]["problems"] == ["The file is empty."]


# ---------- numbers ----------

def test_number_formats():
    assert parse_number("15.80", ",") == (15.8, None)
    assert parse_number("€15.90", ",") == (15.9, None)
    assert parse_number("1,250.00", ",") == (1250.0, None)
    assert parse_number("(25.00)", ",") == (-25.0, None)
    assert parse_number("12,5", ";") == (12.5, None)
    assert parse_number("12,5", ",")[0] is None  # ambiguous in a comma file
    assert parse_number("twelve", ",")[0] is None


# ---------- the checks from the job post ----------

def test_missing_values():
    d = run("001,Dublin,160,160,0,0,0,,0", "002,,160,160,0,0,0,15,0")
    assert messages(d) == ["Missing hourly rate", "Missing store"]


def test_blank_optional_numbers_count_as_zero():
    d = run("001,Dublin,160,160,,,,15.80,")
    assert d["summary"]["ok"] == 1


def test_duplicate_ids_point_at_each_other():
    d = run("001,Dublin,160,160,0,0,0,15,0", "002,Cork,160,160,0,0,0,15,0", " 001 ,Cork,40,40,0,0,0,15,0")
    assert "Employee ID 001 also appears on row 4" in messages(d)
    assert d["summary"]["errors"] == 2


def test_negative_hours_are_errors_and_negative_bonus_is_a_warning():
    d = run("001,Dublin,160,160,0,-8,0,15,0", "002,Cork,160,160,0,0,0,15,(25.00)")
    sev = {r["employee_id"]: r["severity"] for r in d["rows"]}
    assert sev == {"001": "error", "002": "warning"}


def test_unusually_high_overtime_by_hours_and_by_percent():
    d = run("001,Dublin,160,205,45,0,0,15,0", "002,Cork,40,55,15,0,0,15,0")
    assert d["summary"]["warnings"] == 2
    assert any("38% of contracted" in m for m in messages(d))


def test_overtime_threshold_is_configurable():
    d = run("001,Dublin,160,205,45,0,0,15,0", settings=Settings(overtime_max_hours=60, overtime_max_pct_of_contracted=50))
    assert "high_overtime" not in checks(d)


def test_formatting_problems():
    d = run("001,Dublin,160,twelve,0,0,0,15,0", "002,Cork,160,160,0,0,0,15,0,99", "003,Cork,160,160,0,0,0,15")
    assert d["summary"]["errors"] == 3
    assert "Worked hours is not a number ('twelve')" in messages(d)
    assert any("extra: 99" in m for m in messages(d))


# ---------- extra checks ----------

def test_overtime_more_than_worked():
    assert "overtime_vs_worked" in checks(run("001,Dublin,160,150,160,0,0,15,0"))


def test_hours_beyond_contract_not_recorded_as_overtime():
    assert "unrecorded_hours" in checks(run("001,Dublin,160,185,0,0,0,15.50,0"))


def test_working_time_act_average():
    assert "working_time" in checks(run("001,Dublin,160,214,54,0,0,16,0"))


def test_below_minimum_wage_is_a_warning():
    d = run("001,Dublin,100,100,0,0,0,13.20,0")
    assert d["rows"][0]["severity"] == "warning"
    assert "€13.20/h is below the adult minimum wage (€14.15)" in messages(d)[0]


def test_totals_row_is_recognised():
    assert "totals_row" in checks(run("001,Dublin,160,160,0,0,0,15,0", ",Total,160,160,0,0,0,,0"))


# ---------- the issues CSV ----------

def test_issues_csv_keeps_original_values_and_adds_reason():
    d = run("00123,Dún Laoghaire,160,160,0,-8,0,€15.90,0")
    text = d["issues_csv"]
    assert text.startswith("\ufeff")  # so Excel shows fadas
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    assert rows[0][-3:] == ["Severity", "Issue reason", "Source row"]
    assert rows[1][:9] == ["00123", "Dún Laoghaire", "160", "160", "0", "-8", "0", "€15.90", "0"]
    assert rows[1][-2] == "Negative sick hours (-8)"


def test_issues_csv_uses_the_same_delimiter_as_the_input():
    d = validate((SAMPLES / "excel_export.csv").read_bytes())
    assert d["issues_csv"].splitlines()[0].count(";") >= 9


# ---------- the sample files end to end ----------

def test_sample_file_summary():
    d = validate((SAMPLES / "payroll_sample.csv").read_bytes())
    assert d["summary"] == {"total_rows": 25, "ok": 11, "with_issues": 14, "errors": 8, "warnings": 6}


def test_api_endpoint():
    client = TestClient(app)
    with open(SAMPLES / "payroll_sample.csv", "rb") as f:
        res = client.post("/api/validate", files={"file": ("payroll.csv", f, "text/csv")},
                          data={"settings": '{"overtime_max_hours": 100, "overtime_max_pct_of_contracted": 100}'})
    assert res.status_code == 200
    body = res.json()
    assert body["file"]["name"] == "payroll.csv"
    assert body["settings"]["overtime_max_hours"] == 100
