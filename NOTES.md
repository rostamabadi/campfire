# Notes

## Net income, Q1 2026 (2026-01-01 to 2026-03-31)

**(44,480.14)**, a net loss. Net revenue 37,850.50, cost of goods sold 14,272.75, gross profit
23,577.75, operating expenses 68,100.07, operating income (44,522.32), other income 42.18.

## Decisions and assumptions

- **Only posted entries count.** Void JE-009 and JE-025 and draft JE-019 are out. A draft in
  the range is shown as a note: approving JE-019 would move Q1 to (49,480.14).
- **Both end dates are included.** Plain dates, no time zone.
- **The section comes from the subtype, not the type.** Interest Income has type `revenue`
  but sits under Other income. An expense account may sit there too, as a negative line.
- **One sign formula per section.** Income is credits minus debits, costs are debits minus
  credits. Contra revenue comes out negative with no special case, and the JE-020 vendor
  credit reduces Software to 1,099.97.
- **An inactive account keeps its history**, so 6300 Marketing (legacy) is reported.
- **As recorded.** JE-007 puts three months of rent in January. JE-004 only defers revenue.
- **Every income-statement account has a line**, 0.00 when it has no activity.
- **Money is `Decimal`, read from the strings**, and a string in the JSON. An amount given as
  a JSON number is rejected.
- **Bad data blocks the statement only when it could change the totals.** A problem in the
  chart of accounts or a posted entry, such as an unbalanced entry or a type and subtype
  that disagree, returns 500 listing every problem. The same problem in a draft or void
  entry is only a note.
- **Possible duplicates are flagged, not removed.** Two posted entries with the same date
  and identical lines stay in the totals. JE-009 and JE-010 raise nothing because JE-009 is
  already void.
- **No closing entries exist in the data**, so a range across the year end just sums activity.

## How the numbers were checked

- Q1 and each month were worked out line by line from `ledger.json`, separately from the app
  code. The tests compare against those figures, with the working in the comments.
- Two invariants run over 1,035 date ranges: net income equals the net movement in
  balance-sheet accounts (the other half of each entry), and adjacent ranges add up.
- The app repeats the first one on every request. A mismatch returns an error, not numbers.
- `tests/mutation_check.py` plants 20 mistakes one at a time, such as counting drafts or an
  exclusive end date. The tests fail for every one.
- The page lists every journal line under its account, with ignored lines struck out and
  the reason, so each amount can be added up by hand.

## Where AI helped, and where it was wrong

Claude Code helped read the brief, list the traps in the data, and write the code and tests.

- **Wrong:** it assumed float arithmetic would visibly drift on this ledger. It does not:
  `1199.97 - 100.0` prints `1099.97`. A float implementation would pass tests built only on
  these figures, so there is a `0.10 + 0.20` test and a check that the JSON has no numbers.
- **Not trusted:** the tests passed on the first run, which proves little. That is why the
  mistakes are planted on purpose.

## Next

- Better duplicate detection: near matches on nearby dates or with lines split differently.
- Comparative periods, and drill-down from a line to its entries.
- A balance sheet and trial balance from the same per-account totals.
