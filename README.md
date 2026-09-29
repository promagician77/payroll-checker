# Payroll file check

Upload a monthly payroll CSV, see which rows need attention, and download them as a CSV with an "Issue reason" column.

Everything runs on your own computer. Files are checked in memory and never saved or sent anywhere.

## Run it (no technical steps)

You only need **Python 3.10 or newer**. If you don't have it, install it from https://www.python.org/downloads/ (on Windows, tick **"Add python.exe to PATH"** during setup).

- **Windows:** double-click `run-windows.bat`
- **Mac:** double-click `run-mac.command` (the first time, right-click it and choose **Open**)

The first run takes about a minute to set up. After that it starts in a couple of seconds and opens the page in your browser at http://127.0.0.1:8000. Keep the black window open while you use it; close it to stop.

## Using it

1. Drop your CSV on the page, or click **Choose a file**.
2. Read the summary: total rows, how many are OK, how many need attention.
3. Click **Download issues CSV**. It has your original rows, exactly as in your file, plus **Severity**, **Issue reason**, and **Source row**.

Two sample files with deliberate problems are in `web/sample/` and on the page.

## What it checks

| Check | Severity |
|---|---|
| Missing employee ID, store, contracted hours, worked hours, or hourly rate | Error |
| Duplicate employee IDs (each row says where the other one is) | Error |
| Negative hours or rates | Error |
| Negative bonus | Warning |
| Text where a number should be, or rows with too many or too few values | Error |
| Overtime above 40 h or above 25% of contracted hours | Warning |
| Overtime larger than total worked hours | Error |
| Hours over contract that aren't recorded as overtime | Warning |
| Above a 48-hour average week (Organisation of Working Time Act) | Warning |
| Hourly rate below the adult minimum wage (€14.15 from 1 January 2026) | Warning |
| No worked, sick, or holiday hours at all | Warning |
| A totals row mixed in with employees | Warning |

It also copes with the usual file quirks: Excel's hidden BOM, semicolon files with comma decimals (`162,5`), euro signs, thousands separators, accounting negatives like `(25.00)`, Windows-1252 encoding, blank rows, and different header spellings ("Holiday Hours", "Annual Leave", "Emp No", "Pay Rate", and so on).

## Changing the thresholds

Open **Check settings** at the bottom of the page. To make your own defaults permanent, copy `settings.example.json` to `settings.json` and edit the numbers.

## For developers

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                      # 24 tests
python run.py               # http://127.0.0.1:8000, API docs at /api/docs
```

| Path | What's there |
|---|---|
| `app/csvio.py` | Reading files: encoding, delimiter, header matching, number parsing, writing the issues CSV |
| `app/rules.py` | The checks and the summary |
| `app/settings.py` | Thresholds and their defaults |
| `app/main.py` | FastAPI: `POST /api/validate`, `GET /api/settings` |
| `web/` | The page. React with no build step, vendored in `web/vendor/` so it works offline |
| `tests/` | pytest suite |

To add a check, write it in `check_row()` in `app/rules.py`, give it a name in `CHECK_NAMES`, and add a test.

The hosted demo deploys to Vercel as-is (`vercel --prod`); `api/index.py` is its entry point.
