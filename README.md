# Income statement

A small app that shows an income statement (P&L) for Northwind Coffee Roasters for any date
range, built from the chart of accounts and journal entries in `ledger.json`.

The backend is Flask. The frontend is a server-rendered page from the same process, so one
command runs both.

## Run

```
./setup.sh        # once. Installs what is missing and is safe to run again
./run_server.sh   # backend and frontend, on http://127.0.0.1:5001/
```

`run_server.sh` asks which ledger file and which port to use. Press Enter twice for the
original `ledger.json` on port 5001, or on the next free port if 5001 is taken. It prints
the address it serves.

`setup.sh` makes sure [uv](https://docs.astral.sh/uv/) is installed, lets it install Python
3.14 and the packages into `.venv` in this folder, and downloads the browser for the
end-to-end tests. It uses no sudo and does not edit your shell profile.

By hand, with uv already installed (`brew install uv`):

```
uv sync
uv run flask --app app run --port 5001
```

- Page: http://127.0.0.1:5001/ opens on the whole ledger, from the first posted entry to
  the last. Change the dates to see any other range. Under the statement, "Detail" lists
  every journal line by account, with the lines that do not count struck out and the
  reason, so each amount can be added up by hand.
- API: http://127.0.0.1:5001/income-statement?start=2026-01-01&end=2026-03-31

Port 5001 is used because Flask's default, 5000, is taken by AirPlay Receiver on macOS.
`ledger.json` is read on every request, so an edit to it shows up without a restart.

## Other ledgers to try

`ledger.json` is clean, so three sample ledgers in `tests/data` hold the cases it does not.
`./run_server.sh` lists them and lets you pick one. To skip the questions, set the answers:

```
LEDGER_FILE=tests/data/ledger_warnings.json PORT=5002 ./run_server.sh
```

| File | What you see |
| --- | --- |
| `ledger_blocking_errors.json` | No statement. 24 problems, covering every check that blocks: accounts with a reused number, an unknown type or subtype, a type and subtype that disagree or a missing field, and posted entries that do not balance, use an unknown account, have invalid amounts or dates, too few lines, a line with both sides, an unknown status, a reused id or a missing field. |
| `ledger_warnings.json` | A statement with 11 notes: the same problems in draft and void entries, a sound draft, and a possible duplicate. It also has valid but unusual entries: a negative expense, contra revenue that ends positive, an expense under other income, an inactive account, a five-digit account, a zero line, and an entry with no memo. |
| `ledger_unreadable.json` | No statement. The file stops in the middle, so it cannot be read at all. |

## Test

```
./run_all_tests.sh   # unit, integration, end-to-end, then the mutation check
./cicd.sh            # lint and type checks, then everything above
```

| Folder | What it tests |
| --- | --- |
| `tests/unit` | Pure functions on small ledgers built inside the test. No files, no HTTP. |
| `tests/integration` | `ledger.json` loaded from disk, and the HTTP layer through Flask's test client. |
| `tests/e2e` | A real browser against the running app, with Playwright. |

The mutation check plants 20 mistakes, one at a time, in a temporary copy of the project and
confirms that the tests fail for each. Lint is ruff, on the code and the tests. Types are
mypy, on the application code. Neither has any suppression.

By hand:

```
uv run pytest                           # unit and integration
uv run pytest tests/e2e                 # needs: uv run playwright install chromium
uv run python tests/mutation_check.py
uv run ruff check .
uv run mypy
```

## Video walkthrough

`video/walkthrough.webm` is the walkthrough: 4 minutes 25 seconds, without sound, with
captions. It plays in a browser such as Chrome, not in QuickTime. `video/timeline.md` lists
each caption with its time in the video.

A script records it, driving the app in a headless browser with Playwright:

```
uv run python -m video.record_walkthrough   # about 5 minutes. CAPTIONS=0 leaves the captions out
```

It runs `./cicd.sh` first, to show its real output, then records in real time and replaces
the video and the timeline. The pages come from the running app, the code is read from the
project files, and the terminal output is what the commands printed. The script adds the
zoom, an address bar, a pointer and the highlight boxes, and has the app indent its JSON.
The colours of the code come from Pygments, which is installed with pytest.

## Versions

Python 3.14.7, uv 0.12.21, Flask 3.1.3, pytest 9.1.1, Playwright 1.63.0 with pytest-playwright
0.9.0, ruff 0.16.10, mypy 2.4.0, on macOS 26.6.2.

## Code

| File | Role |
| --- | --- |
| `ledger.json` | The data, verbatim from the brief. |
| `checks.py` | The checks on the raw data, and the two value parsers for amounts and dates. |
| `ledger.py` | The data model as dataclasses with `Decimal` amounts, and loading it from the file. |
| `statement.py` | Builds the statement: lists every line per account, sums the counted ones, lays out sections and subtotals, runs the control total, finds warnings. |
| `app.py` | Flask routes, request validation, error responses, money formatting. |
| `templates/statement.html` | The page: date form, errors, warnings, statement, check table, line detail. |
| `tests/` | pytest, in `unit`, `integration` and `e2e`. `builders.py` holds the shared helpers. `mutation_check.py` plants mistakes. |
| `setup.sh`, `run_server.sh`, `run_all_tests.sh`, `cicd.sh` | Set up a Mac, run the app, run every test, run lint and types and every test. |
| `video/` | The walkthrough video, the timeline of its captions, and `record_walkthrough.py`, which records it. |

The path from the dates to the numbers: `app.py` `read_ledger` and `parse_range` →
`statement.py` `income_statement` → `detail_lines_by_account` (which uses `entries_in_range`
to decide what counts) → `build_section` for each section → subtotals → control total →
`statement_json` or the template.

## Response

`GET /income-statement?start=YYYY-MM-DD&end=YYYY-MM-DD`. Both dates are included in the
range. Amounts are decimal strings, never JSON numbers. A negative amount has a minus sign.

```json
{
  "company": "Northwind Coffee Roasters",
  "currency": "USD",
  "start": "2026-01-01",
  "end": "2026-03-31",
  "revenue": {
    "lines": [
      {"account": "4000", "name": "Product Revenue", "amount": "35650.75"},
      {"account": "4100", "name": "Subscription Revenue", "amount": "3000.00"},
      {"account": "4900", "name": "Sales Returns & Discounts", "amount": "-800.25"}
    ],
    "total": "37850.50"
  },
  "cost_of_goods_sold": {"lines": ["..."], "total": "14272.75"},
  "gross_profit": "23577.75",
  "operating_expenses": {"lines": ["..."], "total": "68100.07"},
  "operating_income": "-44522.32",
  "other_income": {"lines": ["..."], "total": "42.18"},
  "net_income": "-44480.14",
  "balance_sheet_movement": {"lines": ["..."], "total": "-44480.14"},
  "warnings": [
    {"code": "draft_not_included", "entry_ids": ["JE-019"], "date": "2026-03-15",
     "memo": "Q1 bonus accrual (pending approval)", "amount": "5000.00", "message": "..."}
  ]
}
```

`balance_sheet_movement` is a check, not a balance sheet. It is debits minus credits on each
balance-sheet account for the same entries. Every entry balances, so its total must equal
`net_income`. If it ever does not, the app returns an error instead of a statement.

Errors always have one shape and list every problem found:

```json
{"errors": [{"code": "invalid_range", "field": "start", "message": "The start date 2026-04-01 is after the end date 2026-03-31."}]}
```

| Status | Codes | When |
| --- | --- | --- |
| 400 | `missing_parameter`, `invalid_date`, `invalid_range` | The request dates. Each names the `field`. |
| 500 | `missing_field`, `unbalanced_entry`, `unknown_account`, `invalid_amount`, `invalid_line`, `too_few_lines`, `unknown_status`, `unknown_type`, `unknown_subtype`, `type_subtype_mismatch`, `invalid_date`, `duplicate_id` | A problem in the ledger data that could change the totals. Each names the `entry_id` or `account`. No numbers are returned. |
| 500 | `unreadable_ledger` | The file is missing, is not JSON, or has the wrong structure. |
| 500 | `control_total_mismatch` | Net income and the balance-sheet movement differ. |
| 404, 405, 500 | `not_found`, `method_not_allowed`, `internal_server_error` | Everything else, in the same shape. |

Warnings ride along with a successful statement and never change the totals:

| Code | When |
| --- | --- |
| `draft_not_included` | A draft entry is dated inside the range. |
| `possible_duplicate` | Two or more posted entries in the range have the same date and identical lines. All stay in the totals. |
| a ledger check's code, such as `unbalanced_entry` | The problem is in a draft or void entry. That entry cannot change the totals, so it is left out and reported, whatever the range. |
