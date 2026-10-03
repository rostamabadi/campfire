# Income statement take-home

A small server-rendered app that shows an income statement (P&L) for Northwind Coffee
Roasters for any date range. Brief:
https://github.com/Campfire-eng/income-statement-take-home

## Priorities

1. **Correct numbers for any date range.** A plain page with right numbers beats
   everything else.
2. **Code that can be changed by hand.** The follow-up session extends this code with AI
   off, on the same ledger. Plain functions and dataclasses, no clever abstractions.
3. **Sized for 2 hours.** No database, auth, Docker, styling work, or features beyond the
   brief. Not built for scale.

## Stack and commands

Python 3.14, uv, Flask (Jinja templates), pytest. No other dependencies without asking.

```
uv sync
uv run flask --app app run --port 8000   # port 5000 is taken by AirPlay on macOS
uv run pytest
```

## Layout

| File | Role |
| --- | --- |
| `ledger.json` | The data, verbatim from the brief. Never edit it. |
| `ledger.py` | Check the raw data, collecting every problem, then load it into dataclasses (`Decimal`, `date`). |
| `statement.py` | Pure functions: sum posted lines per account for a range, lay out sections and subtotals, find warnings. |
| `app.py` | Flask routes, request validation, error responses, money formatting. |
| `templates/statement.html` | Date form, errors, warnings, statement. |
| `tests/` | pytest. `builders.py` builds small ledgers in the `ledger.json` shape. |

Routes: `GET /income-statement?start=YYYY-MM-DD&end=YYYY-MM-DD` returns JSON. `GET /`
renders the HTML page from the same function.

## Accounting rules

- Only `posted` entries count. `draft` and `void` are ignored.
- The range is inclusive at both ends, compared on the entry `date` (plain dates, no time zone).
- The section comes from `subtype`, never from `type`. `balance_sheet` accounts never appear.
- `is_active` is ignored for reporting: an inactive account keeps its history.
- Entries are reported as recorded. No re-accruing, spreading or reclassifying.
- Every income-statement account always gets a line, `0.00` when it has no activity.

| Section | Subtypes, in display order | Line amount |
| --- | --- | --- |
| Revenue | `operating_revenue`, then `contra_revenue` | credits − debits |
| Cost of goods sold | `cogs` | debits − credits |
| Operating expenses | `operating_expense` | debits − credits |
| Other income | `other_income` | credits − debits |

Gross profit = Revenue − Cost of goods sold. Operating income = Gross profit − Operating
expenses. Net income = Operating income + Other income.

The sign of a line comes only from its section's formula. No `abs()`, no flipping by
subtype or account type.

**Contra revenue** has no special-case arithmetic. It uses the Revenue formula, so its
debit balance comes out negative on its own (`"-800.25"` in JSON, `(800.25)` in HTML). It
is listed after the operating revenue accounts. The Revenue subtotal is net of contra and
labelled "Net revenue". There is no separate gross revenue subtotal.

Within a subtype, lines are ordered by account number.

## Money

`Decimal` from the JSON strings, end to end. Never `float`. JSON amounts are strings with
two decimals and a minus sign (`"-44480.14"`). Thousands separators and parentheses for
negatives exist only in the HTML.

## Response shape

```json
{
  "company": "Northwind Coffee Roasters",
  "currency": "USD",
  "start": "2026-01-01",
  "end": "2026-03-31",
  "revenue": {
    "lines": [
      {"account": "4000", "name": "Product Revenue", "amount": "35650.75"},
      {"account": "4900", "name": "Sales Returns & Discounts", "amount": "-800.25"}
    ],
    "total": "37850.50"
  },
  "cost_of_goods_sold": {"lines": [], "total": "14272.75"},
  "gross_profit": "23577.75",
  "operating_expenses": {"lines": [], "total": "68100.07"},
  "operating_income": "-44522.32",
  "other_income": {"lines": [], "total": "42.18"},
  "net_income": "-44480.14",
  "warnings": []
}
```

## Errors

Every error response has one shape, and reports every problem found, not only the first:

```json
{"errors": [{"code": "invalid_range", "field": "start", "message": "The start date 2026-04-01 is after the end date 2026-03-31."}]}
```

- **Request errors, HTTP 400.** `missing_parameter`, `invalid_date`, `invalid_range`. Each
  names the `field`.
- **Ledger errors, HTTP 500.** The ledger is checked once at startup. The app still starts,
  and every statement request returns the full list instead of numbers. No partial
  statements. Checks: `unbalanced_entry`, `unknown_account`, `invalid_amount` (not a decimal
  string, negative, more than two decimals), `invalid_line` (debit and credit both
  non-zero), `unknown_status`, `unknown_subtype`, `invalid_date`, `duplicate_id`. Each names
  the `entry_id` or `account`. The checks apply to every entry, whatever its status. A file
  that is missing, not JSON, or missing a field is one `unreadable_ledger` error.
- Messages are written for an accountant: they name the entry, the accounts and the amounts.
- The HTML page shows the same messages above the statement, with the same status code.
- `GET /` with no query string is a first visit: form only, no error.
- A valid range with no activity is not an error. It is a statement of zeros.

## Warnings

Warnings do not change the totals. They ride along with a successful statement in
`warnings`, and the page shows them in a box above the statement. Only entries dated inside
the requested range are considered.

```json
{"code": "draft_not_included", "entry_ids": ["JE-019"], "date": "2026-03-15",
 "message": "JE-019 (2026-03-15, Q1 bonus accrual (pending approval), 5,000.00) is a draft and is not included in the totals."}
```

- **`draft_not_included`**: one per draft entry in the range. Void entries are not reported:
  they are cancelled and can no longer change the statement.
- **`possible_duplicate`**: two or more `posted` entries with the same date and identical
  lines. They cannot be proven duplicates from the data, so all stay in the totals, as
  recorded. Nothing is dropped automatically. A posted entry whose twin is `void` raises
  nothing: the void is the fix (JE-009, JE-010).
- Duplicate detection is deliberately minimal (exact match, same date). Improving it is
  planned for later.

## Reference figures

Q1 2026 (2026-01-01 to 2026-03-31), worked out by hand from `ledger.json`:

| Line | Amount |
| --- | ---: |
| Net revenue | 37,850.50 |
| Cost of goods sold | 14,272.75 |
| Gross profit | 23,577.75 |
| Operating expenses | 68,100.07 |
| Operating income | (44,522.32) |
| Other income | 42.18 |
| Net income | (44,480.14) |

Net income by month: January (21,529.65), February (13,230.25), March (9,720.24).

## Tests

- Q1 2026, every line and subtotal, against the hand-worked figures.
- One test per data trap, each on a tiny ledger built inside the test: void and draft
  excluded, inactive account included, a credit to an expense nets down, contra revenue
  reduces revenue, other income placed by subtype, balance-sheet-only entries have no
  effect, entries with more than two lines, inclusive range ends, unsorted input.
- Invariants on the real ledger over many ranges: sub-ranges add up to the whole range, and
  net income equals the net movement in balance-sheet accounts.
- Warnings: drafts and possible duplicates, and that neither changes the totals.
- Each ledger check and each request error, through the Flask test client.
- Expected values are worked out by hand, never copied from the app's output.

## Working agreements

- Commit after each working step, in small commits, on `main`. Push only when asked.
- When a data assumption is made, add it to `NOTES.md` (one page at most).
- When AI output turns out wrong or is corrected, add a line to the AI log in `NOTES.md`.
- Deliverables: `README.md` (run commands and versions), `NOTES.md`, code and tests.
