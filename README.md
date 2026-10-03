# Income statement

A small app that shows an income statement (P&L) for Northwind Coffee Roasters for any date
range, built from the chart of accounts and journal entries in `ledger.json`.

The backend is Flask. The frontend is a server-rendered page from the same process, so one
command runs both.

## Run

You need [uv](https://docs.astral.sh/uv/) (`brew install uv`). It installs Python 3.14 and
the dependencies on the first run.

```
uv sync
uv run flask --app app run --port 5001
```

- Page: http://127.0.0.1:5001/
- API: http://127.0.0.1:5001/income-statement?start=2026-01-01&end=2026-03-31

Port 5001 is used because Flask's default, 5000, is taken by AirPlay Receiver on macOS.

## Test

```
uv run pytest
```

## Versions

Python 3.14.7, uv 0.12.21, Flask 3.1.3, pytest 9.1.1, on macOS 26.6.2.

## Code

| File | Role |
| --- | --- |
| `ledger.json` | The data, verbatim from the brief. |
| `ledger.py` | Checks the raw data, then loads it into dataclasses with `Decimal` amounts. |
| `statement.py` | Builds the statement: sums posted lines per account for the range, lays out sections and subtotals, finds warnings. |
| `app.py` | Flask routes, request validation, error responses, money formatting. |
| `templates/statement.html` | The page: date form, errors, warnings, statement. |
| `tests/` | pytest. `builders.py` builds small ledgers in the `ledger.json` shape. |

The path from the dates to the numbers: `app.py` `parse_range` → `statement.py`
`income_statement` → `entries_in_range` → `account_totals` → `build_section` for each
section → subtotals → `statement_json` or the template.

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
    {"code": "draft_not_included", "entry_ids": ["JE-019"], "date": "2026-03-15", "message": "..."}
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

A bad request returns 400. A problem in the ledger data returns 500 and no numbers.
