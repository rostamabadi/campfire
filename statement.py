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

from checks import problem
from ledger import Entry, Ledger

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class DetailLine:
    """One journal line, as listed under its account in the detail."""
    date: date
    entry_id: str
    memo: str
    debit: Decimal
    credit: Decimal
    counted: bool
    reason: str  # why it is not counted: "void", "draft" or "outside the range". Empty when counted


@dataclass(frozen=True)
class StatementLine:
    account: str  # account number
    name: str
    amount: Decimal
    debits: Decimal  # total of the counted debits
    credits: Decimal  # total of the counted credits
    detail: list[DetailLine]  # every line in the ledger on this account, counted or not


@dataclass(frozen=True)
class Section:
    title: str  # the heading, such as "Revenue"
    total_label: str  # the label of the subtotal, such as "Net revenue"
    credit_normal: bool  # True: lines are credits minus debits. False: debits minus credits
    lines: list[StatementLine]
    total: Decimal


@dataclass(frozen=True)
class IncomeStatement:
    company: str
    currency: str  # the currency of the amounts on the statement
    ledger_currency: str  # the currency of the ledger. The control total and the detail stay in it
    rate: Decimal  # what one unit of the ledger's currency is worth in `currency`. 1 when not converted
    start: date
    end: date
    revenue: Section
    cost_of_goods_sold: Section
    gross_profit: Decimal
    operating_expenses: Section
    operating_income: Decimal
    other_income: Section
    net_income: Decimal
    balance_sheet_movement: Section  # the control total: its total always equals net_income
    warnings: list[dict]

    @property
    def sections(self) -> list[Section]:
        """The four sections of the statement, in the order they are shown."""
        return [self.revenue, self.cost_of_goods_sold, self.operating_expenses, self.other_income]


class ControlTotalError(Exception):
    """Net income and the movement in balance-sheet accounts disagree, so one of them is wrong."""

    def __init__(self, error: dict):
        super().__init__(error["message"])
        self.error = error


def posted_date_span(ledger: Ledger) -> tuple[date, date] | None:
    """The dates of the first and the last posted entry, or None if nothing is posted."""
    dates = [entry.date for entry in ledger.entries if entry.status == "posted"]
    if not dates:
        return None
    return min(dates), max(dates)


def entries_in_range(ledger: Ledger, start: date, end: date, status: str) -> list[Entry]:
    """Entries with the given status dated from start to end, both days included."""
    return [
        entry for entry in ledger.entries
        if entry.status == status and start <= entry.date <= end
    ]


def detail_lines_by_account(ledger: Ledger, start: date, end: date) -> dict[str, list[DetailLine]]:
    """Every journal line in the ledger, grouped by account number, oldest first.

    Each line records whether it counts toward the range and, if not, why not. Every amount
    on the statement is the sum of the counted lines here, and the page lists these same
    lines under each account, so what is shown and what is summed cannot differ.
    """
    counted_ids = {entry.id for entry in entries_in_range(ledger, start, end, "posted")}

    lines_by_account: dict[str, list[DetailLine]] = {}
    for entry in sorted(ledger.entries, key=lambda entry: entry.date):
        if entry.id in counted_ids:
            reason = ""
        elif entry.status != "posted":
            reason = entry.status  # "draft" or "void"
        else:
            reason = "outside the range"

        for line in entry.lines:
            lines_by_account.setdefault(line.account, []).append(DetailLine(
                date=entry.date,
                entry_id=entry.id,
                memo=entry.memo,
                debit=line.debit,
                credit=line.credit,
                counted=reason == "",
                reason=reason,
            ))
    return lines_by_account


def build_section(
    ledger: Ledger,
    lines_by_account: dict[str, list[DetailLine]],
    title: str,
    total_label: str,
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
        # Shorter numbers first, so that 6000 comes before 10000. Plain text order would not.
        for account in sorted(accounts, key=lambda account: (len(account.number), account.number)):
            detail = lines_by_account.get(account.number, [])
            debits = sum((line.debit for line in detail if line.counted), ZERO)
            credits = sum((line.credit for line in detail if line.counted), ZERO)
            amount = credits - debits if credit_normal else debits - credits
            lines.append(StatementLine(
                account=account.number,
                name=account.name,
                amount=amount,
                debits=debits,
                credits=credits,
                detail=detail,
            ))

    total = sum((line.amount for line in lines), ZERO)
    return Section(title=title, total_label=total_label, credit_normal=credit_normal, lines=lines, total=total)


def find_warnings(ledger: Ledger, start: date, end: date) -> list[dict]:
    """Things a reader should know about the range. Warnings never change the totals.

    The statement adds the ledger's own warnings to these: problems in draft and void entries.
    """
    warnings = []

    for entry in entries_in_range(ledger, start, end, "draft"):
        amount = sum((line.debit for line in entry.lines), ZERO)
        warnings.append(problem(
            "draft_not_included",
            f"{entry.id} ({entry.date}, {entry.memo}, {amount:,.2f}) is a draft and is not included in the totals.",
            entry_ids=[entry.id],
            date=entry.date.isoformat(),
            memo=entry.memo,
            amount=f"{amount:.2f}",
        ))

    # Posted entries with the same date and identical lines may have been entered twice.
    # That cannot be proven from the data, so they stay in the totals, as recorded.
    ids_by_content: dict[tuple, list[str]] = {}
    for entry in entries_in_range(ledger, start, end, "posted"):
        lines = sorted((line.account, line.debit, line.credit) for line in entry.lines)
        content = (entry.date, tuple(lines))
        ids_by_content.setdefault(content, []).append(entry.id)

    for (entry_date, _lines), entry_ids in ids_by_content.items():
        if len(entry_ids) > 1:
            warnings.append(problem(
                "possible_duplicate",
                f"{' and '.join(entry_ids)} are posted on {entry_date} with identical lines. "
                f"All of them are included in the totals.",
                entry_ids=entry_ids,
                date=entry_date.isoformat(),
            ))

    return warnings


def results(
    revenue: Section, cost_of_goods_sold: Section, operating_expenses: Section, other_income: Section
) -> tuple[Decimal, Decimal, Decimal]:
    """Gross profit, operating income and net income, from the totals of the four sections."""
    gross_profit = revenue.total - cost_of_goods_sold.total
    operating_income = gross_profit - operating_expenses.total
    net_income = operating_income + other_income.total
    return gross_profit, operating_income, net_income


def income_statement(ledger: Ledger, start: date, end: date) -> IncomeStatement:
    """The income statement for posted entries dated from start to end, both days included."""
    lines_by_account = detail_lines_by_account(ledger, start, end)

    def section(title: str, total_label: str, subtypes: list[str], credit_normal: bool) -> Section:
        return build_section(ledger, lines_by_account, title, total_label, subtypes, credit_normal)

    # Each section is defined here, once: its heading, its subtotal label, the subtypes it
    # holds in display order, and its sign. The page reads all of that from the section.
    revenue = section("Revenue", "Net revenue", ["operating_revenue", "contra_revenue"], credit_normal=True)
    cost_of_goods_sold = section("Cost of goods sold", "Total cost of goods sold", ["cogs"], credit_normal=False)
    operating_expenses = section(
        "Operating expenses", "Total operating expenses", ["operating_expense"], credit_normal=False
    )
    other_income = section("Other income", "Total other income", ["other_income"], credit_normal=True)

    gross_profit, operating_income, net_income = results(revenue, cost_of_goods_sold, operating_expenses, other_income)

    # The control total. Every entry balances, so the balance-sheet lines of the same entries
    # must net to the same amount as the income statement. If they do not, an account was
    # left out, counted twice or given the wrong sign, and no statement is returned.
    balance_sheet_movement = section(
        "Balance-sheet accounts", "Total movement", ["balance_sheet"], credit_normal=False
    )
    if balance_sheet_movement.total != net_income:
        raise ControlTotalError(problem(
            "control_total_mismatch",
            f"For {start} to {end}, net income is {net_income:,.2f} but the balance-sheet accounts "
            f"moved by {balance_sheet_movement.total:,.2f}. These must be equal, so the statement is not shown.",
        ))

    return IncomeStatement(
        company=ledger.company,
        currency=ledger.currency,
        ledger_currency=ledger.currency,
        rate=Decimal("1"),
        start=start,
        end=end,
        revenue=revenue,
        cost_of_goods_sold=cost_of_goods_sold,
        gross_profit=gross_profit,
        operating_expenses=operating_expenses,
        operating_income=operating_income,
        other_income=other_income,
        net_income=net_income,
        balance_sheet_movement=balance_sheet_movement,
        warnings=ledger.warnings + find_warnings(ledger, start, end),
    )
