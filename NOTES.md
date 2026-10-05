# Notes

## Q1 2026 net income: (44,480.14)

A net loss, for 2026-01-01 to 2026-03-31.

| | Amount |
| --- | ---: |
| Net revenue | 37,850.50 |
| Cost of goods sold | 14,272.75 |
| **Gross profit** | **23,577.75** |
| Operating expenses | 68,100.07 |
| **Operating income** | **(44,522.32)** |
| Other income | 42.18 |
| **Net income** | **(44,480.14)** |

## Decisions and assumptions

- **Only posted entries count.** Void JE-009, JE-025 and draft JE-019 are out. A draft in the
  range is shown as a note: approving JE-019 would make Q1 (49,480.14).
- **Both end dates are included.** Plain dates, no time zone.
- **The section comes from the subtype, not the type.** Interest Income has type `revenue`
  but sits under Other income. An expense may sit there too, as a negative line.
- **One sign formula per section.** Income is credits minus debits, costs the reverse. Contra
  revenue comes out negative unaided, and the JE-020 credit cuts Software to 1,099.97.
- **An inactive account keeps its history**: 6300 Marketing (legacy) is reported. Every
  income-statement account has a line, 0.00 when idle.
- **As recorded.** JE-007 puts three months of rent in January. JE-004 only defers revenue.
- **Money is `Decimal`, read from the strings**, and a string in the JSON.
- **Bad data blocks only when it could change the totals.** A problem in the chart of
  accounts or a posted entry returns 500 with every problem. In a draft or void entry it is
  only a note.
- **Possible duplicates are flagged, not removed.** Two posted entries with the same date
  and lines both stay. JE-009 and JE-010 raise nothing, since JE-009 is void.
- **Another currency is a restatement at one rate**, not the rate on each entry's date. Each
  account line is converted and rounded half up, and the totals are added up from those, so
  the statement adds up: Q1 is (40,032.13) in EUR at 0.9. The check and the detail stay in USD.
- **No closing entries exist**, so a range across the year end just sums activity.

## How the numbers were checked

- Q1 and each month were worked out by hand from `ledger.json`, apart from the code. The
  tests compare against those figures.
- Two invariants run over 1,035 date ranges: net income equals the movement in
  balance-sheet accounts, and adjacent ranges add up. The app repeats the first on every
  request.
- `tests/mutation_check.py` plants 30 mistakes one at a time. The tests fail for each.
- The page lists every journal line by account, ignored ones struck out with the reason, so
  any amount can be re-added by hand.

## Where AI helped, and where it was wrong

Claude Code helped read the brief, list the traps in the data, and write the code and tests.

- **Float drift:** it assumed floats would visibly drift on this ledger. They do not, so a
  `0.10 + 0.20` test covers it.
- **A test expectation:** it expected 9 struck-out lines for Q1. A recount by hand gave 10.
- **A label:** its first warning box said "Not reflected in the totals", false for possible
  duplicates.
- **A stale check:** it planted mistakes once, then added four rules without rerunning.
- **A commit that claimed too much:** two file writes failed unnoticed, so a commit message
  described changes it did not contain.
- **A form label:** its currency list sat inside its label, so the label's text included
  every option. A browser test caught it.
- **Overruled:** it proposed blocking on a bad draft, and hiding out-of-range lines.
- **Not trusted:** tests that pass first time prove little, so mistakes are planted.

## Next

- Better duplicate detection: near matches on nearby dates or with lines split differently.
- Comparative periods, a balance sheet and a trial balance from the same per-account lines.
