"""Build an income statement for a date range from the ledger.

The rules, in one place:
- Only posted entries count. The date range is inclusive at both ends.
- An account's section comes from its subtype, never from its type.
- Revenue and other income lines are credits minus debits.
  Cost of goods sold and operating expense lines are debits minus credits.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ledger import Entry, Ledger

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class StatementLine:
    account: str  # account number
    name: str
    amount: Decimal


@dataclass(frozen=True)
class Section:
    lines: list[StatementLine]
    total: Decimal


@dataclass(frozen=True)
class IncomeStatement:
    company: str
    currency: str
    start: date
    end: date
    revenue: Section
    cost_of_goods_sold: Section
    gross_profit: Decimal
    operating_expenses: Section
    operating_income: Decimal
    other_income: Section
    net_income: Decimal
    warnings: list[dict]


class ControlTotalError(Exception):
    """Net income and the movement in balance-sheet accounts disagree, so one of them is wrong."""

    def __init__(self, error: dict):
        super().__init__(error["message"])
        self.error = error


def entries_in_range(ledger: Ledger, start: date, end: date, status: str) -> list[Entry]:
    """Entries with the given status dated from start to end, both days included."""
    return [
        entry for entry in ledger.entries
        if entry.status == status and start <= entry.date <= end
    ]


def account_totals(entries: list[Entry]) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """Total debits and total credits per account number across the given entries."""
    debit_totals = {}
    credit_totals = {}
    for entry in entries:
        for line in entry.lines:
            debit_totals[line.account] = debit_totals.get(line.account, ZERO) + line.debit
            credit_totals[line.account] = credit_totals.get(line.account, ZERO) + line.credit
    return debit_totals, credit_totals


def build_section(
    ledger: Ledger,
    debit_totals: dict[str, Decimal],
    credit_totals: dict[str, Decimal],
    subtypes: list[str],
    credit_normal: bool,
) -> Section:
    """One section of the statement: a line for every account of the given subtypes, and their total.

    Lines follow the order of `subtypes`, then account number. `credit_normal` sets the sign:
    True means credits minus debits (income), False means debits minus credits (costs).
    """
    lines = []
    for subtype in subtypes:
        accounts = [account for account in ledger.accounts.values() if account.subtype == subtype]
        for account in sorted(accounts, key=lambda account: account.number):
            debits = debit_totals.get(account.number, ZERO)
            credits = credit_totals.get(account.number, ZERO)
            amount = credits - debits if credit_normal else debits - credits
            lines.append(StatementLine(account=account.number, name=account.name, amount=amount))

    total = sum((line.amount for line in lines), ZERO)
    return Section(lines=lines, total=total)


def find_warnings(ledger: Ledger, start: date, end: date) -> list[dict]:
    """Things a reader should know about the range. Warnings never change the totals."""
    warnings = []

    for entry in entries_in_range(ledger, start, end, "draft"):
        amount = sum((line.debit for line in entry.lines), ZERO)
        warnings.append({
            "code": "draft_not_included",
            "entry_ids": [entry.id],
            "date": entry.date.isoformat(),
            "message": f"{entry.id} ({entry.date}, {entry.memo}, {amount:,.2f}) is a draft "
                       f"and is not included in the totals.",
        })

    # Posted entries with the same date and identical lines may have been entered twice.
    # That cannot be proven from the data, so they stay in the totals, as recorded.
    ids_by_content = {}
    for entry in entries_in_range(ledger, start, end, "posted"):
        lines = sorted((line.account, line.debit, line.credit) for line in entry.lines)
        content = (entry.date, tuple(lines))
        ids_by_content.setdefault(content, []).append(entry.id)

    for (entry_date, _lines), entry_ids in ids_by_content.items():
        if len(entry_ids) > 1:
            warnings.append({
                "code": "possible_duplicate",
                "entry_ids": entry_ids,
                "date": entry_date.isoformat(),
                "message": f"{' and '.join(entry_ids)} are posted on {entry_date} with identical lines. "
                           f"All of them are included in the totals.",
            })

    return warnings


def income_statement(ledger: Ledger, start: date, end: date) -> IncomeStatement:
    """The income statement for posted entries dated from start to end, both days included."""
    posted = entries_in_range(ledger, start, end, "posted")
    debit_totals, credit_totals = account_totals(posted)

    revenue = build_section(
        ledger, debit_totals, credit_totals, ["operating_revenue", "contra_revenue"], credit_normal=True
    )
    cost_of_goods_sold = build_section(ledger, debit_totals, credit_totals, ["cogs"], credit_normal=False)
    operating_expenses = build_section(
        ledger, debit_totals, credit_totals, ["operating_expense"], credit_normal=False
    )
    other_income = build_section(ledger, debit_totals, credit_totals, ["other_income"], credit_normal=True)

    gross_profit = revenue.total - cost_of_goods_sold.total
    operating_income = gross_profit - operating_expenses.total
    net_income = operating_income + other_income.total

    # The control total. Every entry balances, so the balance-sheet lines of the same entries
    # must net to the same amount as the income statement. If they do not, an account was
    # left out, counted twice or given the wrong sign, and no statement is returned.
    balance_sheet_movement = build_section(
        ledger, debit_totals, credit_totals, ["balance_sheet"], credit_normal=False
    )
    if balance_sheet_movement.total != net_income:
        raise ControlTotalError({
            "code": "control_total_mismatch",
            "message": f"For {start} to {end}, net income is {net_income:,.2f} but the balance-sheet "
                       f"accounts moved by {balance_sheet_movement.total:,.2f}. These must be equal, "
                       f"so the statement is not shown.",
        })

    return IncomeStatement(
        company=ledger.company,
        currency=ledger.currency,
        start=start,
        end=end,
        revenue=revenue,
        cost_of_goods_sold=cost_of_goods_sold,
        gross_profit=gross_profit,
        operating_expenses=operating_expenses,
        operating_income=operating_income,
        other_income=other_income,
        net_income=net_income,
        warnings=find_warnings(ledger, start, end),
    )
