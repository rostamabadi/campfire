# Walkthrough timeline

| Time | On screen |
| --- | --- |
| 0:00 | [Income statement] |
| 0:03 | The page opens on the whole ledger, from the first posted entry to the last. |
| 0:10 | Q1 2026, January 1 to March 31. Both days are included. |
| 0:17 | A draft dated inside the range is shown as a note and left out of the totals. |
| 0:24 | Returns and discounts are contra revenue: a negative line, so the subtotal is net revenue. |
| 0:31 | The vendor credit lowers Software to 1,099.97. The inactive Marketing account keeps its history. |
| 0:38 | Net income for Q1 is (44,480.14), a net loss. It matches the figure worked out by hand. |
| 0:46 | The control total: the balance-sheet accounts moved by the same amount. The app checks this on every request. |
| 0:54 | The detail lists every journal line by account. Lines that do not count are struck out, with the reason. |
| 1:02 | Product Revenue: December and April are outside the range, JE-009 is void. The rest add up to 35,650.75. |
| 1:11 | Any range works. January alone is a loss of 21,529.65, with three months of rent, as recorded. |
| 1:20 | A start date after the end date gives an error, and no statement. |
| 1:27 | The API returns the same statement as JSON. Amounts are decimal strings, never floats. |
| 1:33 | It carries the control total and the warnings too. |
| 1:38 | A sample ledger with bad data in draft and void entries. The statement is shown, with notes. |
| 1:46 | Bad data in the accounts or in a posted entry could change the totals. Every problem is listed, and no numbers. |
| 1:57 | [The code path] |
| 2:00 | Both routes do the same: read the ledger, then build the statement for the dates in the query string. |
| 2:08 | The file is read and checked on every request. |
| 2:13 | A problem in a posted entry is an error. In a draft or void entry it is a warning, and the entry is left out. |
| 2:24 | Amounts go from the JSON strings straight into Decimal, never through float. |
| 2:29 | The two dates are parsed. A missing, invalid or reversed range is a 400 error. |
| 2:36 | income_statement defines the four sections once: heading, subtotal label, subtypes and sign. |
| 2:42 | A line counts when its entry is posted and dated inside the range. |
| 2:48 | Every journal line is listed under its account, with whether it counts and why not. |
| 2:55 | An account's amount is the sum of its counted lines. The sign comes only from the section. |
| 3:03 | Three subtotals, then the control total. If the two figures differ, there is an error and no statement. |
| 3:11 | Money is formatted at the edge: plain strings in JSON, separators and parentheses on the page. |
| 3:19 | [The checks] |
| 3:22 | Expected values are worked out by hand from ledger.json. The comments show the working. |
| 3:28 | Invariants over many date ranges: net income equals the balance-sheet movement, and adjacent ranges add up. |
| 3:36 | The mutation check plants 20 mistakes, one at a time, and confirms the tests fail for each. |
| 3:43 | cicd.sh runs lint, types, every test and the mutation check. |
| 3:49 | [How it was built] |
| 3:52 | Claude Code helped read the brief, list the traps in the data, and write the code and tests. |
| 4:00 | CLAUDE.md holds the decisions it works from, and the working agreements. |
| 4:06 | Changes are made on branches and merged through pull requests, without squashing. |
| 4:11 | Where the AI was wrong is logged in NOTES.md. Tests that pass first time prove little, so mistakes are planted. |
| 4:20 | [Q1 2026 net income: (44,480.14)] |
