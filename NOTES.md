# Notes

## Net income, Q1 2026 (2026-01-01 to 2026-03-31)

**(44,480.14)**, a net loss. Net revenue 37,850.50, cost of goods sold 14,272.75, gross profit
23,577.75, operating expenses 68,100.07, operating income (44,522.32), other income 42.18.

## Decisions and assumptions

- **Only posted entries count.** Void JE-009 and JE-025 and draft JE-019 are out. A draft in
  the range is shown as a note: approving JE-019 would move Q1 to (49,480.14).
- **Both end dates are included.** Plain dates, no time zone.
- **The section comes from the subtype, not the type.** Interest Income has type `revenue`
  but sits under Other income.
- **One sign formula per section.** Income is credits minus debits, costs are debits minus
  credits. Contra revenue comes out negative with no special case, and the JE-020 vendor
  credit reduces Software to 1,099.97.
- **An inactive account keeps its history**, so 6300 Marketing (legacy) is reported.
- **As recorded.** JE-007 puts three months of rent in January. JE-004 only defers revenue.
- **Every income-statement account has a line**, 0.00 when it has no activity.
- **Money is `Decimal`, read from the strings**, and a string in the JSON. An amount given as
  a JSON number is rejected.
- **Bad data blocks the statement.** An unbalanced entry, an entry with fewer than two lines,
  unknown account, invalid amount or date, unknown status, type or subtype, or reused id
  returns 500 listing every problem, on the page too. A partial statement could be wrong
  without looking wrong.
- **Type and subtype must agree.** A `revenue` account filed as `balance_sheet` would drop
  off the statement without any sign, so that is an error too.
- **Possible duplicates are flagged, not removed.** Two posted entries with the same date
  and identical lines stay in the totals, since it cannot be proven from the data. JE-009
  and JE-010 raise nothing because JE-009 is already void.
- **No closing entries exist in the data**, so a range across the year end just sums activity.

## How the numbers were checked

- Q1 and each month were worked out line by line from `ledger.json`, separately from the app
  code. The tests compare against those figures, with the working in the comments.
- Two invariants run over 1,035 date ranges: net income equals the net movement in
  balance-sheet accounts (the other half of each entry), and adjacent ranges add up.
- Twelve rules were broken one at a time, such as counting drafts, an exclusive end date,
  dropping inactive accounts and `abs()` on contra. Every one made tests fail.
- The running app's page and JSON were compared with the hand-worked figures.

## Where AI helped, and where it was wrong

Claude Code helped read the brief, list the traps in the data, and write the code and tests.

- **Wrong:** it assumed float arithmetic would visibly drift on this ledger. It does not:
  `1199.97 - 100.0` prints `1099.97`. A float implementation would pass tests built only on
  these figures, so there is a `0.10 + 0.20` test and a check that the JSON has no numbers.
- **Wrong:** its first page titled the warning box "Not reflected in the totals", which is
  false for possible duplicates, since those are included.
- **Not trusted:** the tests passed on the first run, which proves little. That is why the
  rules were broken on purpose, and why the Q1 figures came from the ledger, not the app.

## Next

- Better duplicate detection: near matches on nearby dates or with lines split differently.
- Comparative periods, and drill-down from a line to its entries.
- A balance sheet and trial balance from the same per-account totals.
