# Income statement take-home

A small server-rendered app that shows an income statement (P&L) for Northwind Coffee
Roasters for any date range, in the ledger's US dollars or converted to euros or pounds. Brief:
https://github.com/Campfire-eng/income-statement-take-home

This file holds the decisions and the working agreements. Each fact has one home:

| Fact | Where |
| --- | --- |
| Commands, versions, code map, code path | `README.md` |
| Response shape, error and warning codes | `README.md` |
| The Q1 result, the assumptions, how it was checked | `NOTES.md` |
| Why the code is the way it is, and how to work on it | here |

## Priorities

1. **Correct numbers for any date range.** A plain page with right numbers beats
   everything else.
2. **Code that can be changed by hand.** The follow-up session extends this code with AI
   off, on the same ledger. Plain functions and dataclasses, no clever abstractions.
3. **Sized for 2 hours.** No database, auth, Docker, styling work, or features beyond the
   brief. Not built for scale.

Stack: Python 3.14, uv, Flask with Jinja templates, pytest, Playwright for the browser
tests, ruff for lint, mypy for types. No other dependencies without asking.

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
expenses. Net income = Operating income + Other income. These three formulas live in
`results`, which the recorded statement and a converted one both use.

- **Sign.** The sign of a line comes only from its section's formula. No `abs()`, no
  flipping by subtype or account type.
- **Contra revenue** has no special-case arithmetic. Its debit balance comes out negative on
  its own. It is listed after the operating revenue accounts, and the Revenue subtotal is
  net of it, labelled "Net revenue".
- **Order.** Within a subtype, lines are ordered by account number, shorter numbers first,
  so that 6000 comes before 10000.
- **Sections are defined once**, in `income_statement`: heading, subtotal label, subtypes
  and sign. The page reads all of that from the `Section`. A new section also needs its
  subtypes in `checks.py`, a key in `statement_json`, a row in the template's table, and a
  place in `results` and in `IncomeStatement.sections`. `convert_statement` unpacks exactly
  the sections listed there, so it fails loudly until the new one is handled.

## Money

`Decimal` from the JSON strings, end to end. Never `float`. JSON amounts are strings with
two decimals and a minus sign. Thousands separators and parentheses for negatives exist
only in the HTML. An amount must be below 10^15, which keeps every sum far below the 28
digits at which Decimal would round.

## Currency

The ledger is in US dollars. A statement can be shown in euros or pounds, at one rate for the
whole range. It is a restatement for the reader, not accounting for exchange differences,
and the one feature beyond the brief.

- **Rate.** What one dollar is worth in the other currency, so amounts are multiplied by it.
  Defaults: 0.9 for EUR, 0.7 for GBP. A typed rate replaces the default. It must be above 0
  and below 1,000,000, with at most 6 decimal places. The currencies and their defaults are
  one list, `CURRENCIES` in `currency.py`.
- **Each account line is converted once**, rounded half up to the cent. Every subtotal and
  result is then added up from the converted lines. A statement that does not add up reads
  as wrong: with every figure converted on its own, Q1 at 0.9 shows a gross profit of
  21,219.98 under 34,065.45 − 12,845.48, which is 21,219.97.
- **The price**: converted net income can differ by a few cents from recorded net income
  times the rate.
- **The control total, the check table, the detail and the warnings are never converted.**
  They stay in the ledger's currency and say so. The control total runs first, on the
  amounts as recorded. Converted line by line, the balance-sheet accounts would no longer add
  up to net income to the cent.
- **Exact arithmetic.** An amount times a rate is worked out with 50 digits, then rounded
  once. A result of `-0.00` becomes `0.00`.
- **No conversion is the default.** Without a currency, or with the ledger's own, the
  statement is returned as built. A rate sent with the ledger's own currency is an error,
  not ignored. A ledger that is not in USD is never converted: the rates are per dollar.
- **No JavaScript.** A blank rate means the default, which each option in the list states.
  A typed rate stays in the box when the currency is changed.

## Bad data

- The ledger file is read and checked on every request, so an edit shows up without a
  restart.
- **What blocks.** A problem blocks the statement when it could change the totals: any
  problem in the chart of accounts, in a `posted` entry, or in an entry whose status is
  missing or unknown. The response is every problem found, and no numbers.
- **What only warns.** A problem in a `draft` or `void` entry. That entry is left out of
  the ledger and the problem is reported on every statement.
- **Type and subtype must agree.** Asset, liability and equity accounts are `balance_sheet`.
  Revenue accounts are `operating_revenue`, `contra_revenue` or `other_income`. Expense
  accounts are `cogs`, `operating_expense` or `other_income`. Without this a misfiled
  account would drop off the statement, or onto it, without any sign.
- Every error and warning is built by `checks.problem`: a code, where it is, a message
  written for an accountant.

## Duplicates and drafts

- A reused entry id is a ledger error.
- Two or more `posted` entries with the same date and identical lines are a *possible*
  duplicate. That cannot be proven from the data, so all stay in the totals, as recorded,
  and a warning is shown. A posted entry whose twin is `void` raises nothing: the void is
  the fix (JE-009, JE-010). Detection is deliberately minimal. Improving it is planned.
- A draft dated inside the range is shown as a warning. Void entries are not: they are
  cancelled and can no longer change the statement.

## Control total

On every request, net income must equal the net movement (debits − credits) in
balance-sheet accounts for the same entries. Every entry balances, so the two can only
differ if the code left an account out, counted it twice or gave it the wrong sign. Then
the response is an error with both figures, and no statement. It does not catch a line in
the wrong section, or a wrong date or status filter. The movement is shown on the page in a
collapsed "Check" table and returned as `balance_sheet_movement`. It is not a balance
sheet: there are no balances as of a date.

## Detail on the page

A second collapsed section lists every journal line by account, so that a reader can redo
every sum by hand.

- One collapsible block per account, collapsed by default, in statement order, then the
  balance-sheet accounts. Every line in the ledger on that account is listed, whatever its
  status or date.
- A line counts when its entry is posted and dated inside the range. A line that does not
  count is struck out and says why: `void`, `draft` or `outside the range`. When both apply,
  the status is the reason shown.
- Every amount on the statement is the sum of the counted lines listed, so what is shown
  and what is summed cannot differ. `detail_lines_by_account` builds the lines.
- It is on the page only. The JSON response does not carry it.

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

Q1 2026 converted, worked out by hand from the lines: net income is (40,032.13) in EUR at
0.9 and (31,136.10) in GBP at 0.7.

## Tests

- `tests/unit`: pure functions on small ledgers built inside the test. One test per rule
  and per data trap. No files, no HTTP.
- `tests/integration`: `ledger.json` from disk against the hand-worked figures, invariants
  over many ranges, and the HTTP layer through Flask's test client.
- `tests/e2e`: a real browser with Playwright. Run on their own, they need a browser.
- Expected values are worked out by hand, never copied from the app's output.
- `tests/mutation_check.py` plants one mistake at a time in a copy of the project and
  confirms the tests fail. It matches exact lines of source, so update it when those lines
  change, and add a mistake there when a new rule is added.

## Working agreements

- Every change goes on a branch, never directly on `main`. Commit in small steps, push the
  branch, open a pull request and merge it with a merge commit, not a squash: the brief
  asks for real history.
- Run `./cicd.sh` before merging: lint, types, then every test. Fix what it reports. No
  suppressions such as `# type: ignore` or `# noqa`.
- When a data assumption is made, add it to `NOTES.md` (one page at most).
- When AI output turns out wrong or is corrected, add a line to the AI log in `NOTES.md`.
- When a fact changes, change it in its one home, listed at the top of this file.
