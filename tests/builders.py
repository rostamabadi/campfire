"""Helpers shared by the tests: small ledgers in the ledger.json shape, and ways to read a statement."""

from datetime import date
from pathlib import Path

from ledger import LedgerError, parse_ledger
from statement import income_statement

LEDGER_PATH = Path(__file__).parent.parent / "ledger.json"


def account(number, name, type, subtype, is_active=True):
    return {"number": number, "name": name, "type": type, "subtype": subtype, "is_active": is_active}


CHART = [
    account("1000", "Cash", "asset", "balance_sheet"),
    account("1100", "Accounts Receivable", "asset", "balance_sheet"),
    account("2000", "Accounts Payable", "liability", "balance_sheet"),
    account("4000", "Sales", "revenue", "operating_revenue"),
    account("4900", "Returns", "revenue", "contra_revenue"),
    account("5000", "Cost of Goods Sold", "expense", "cogs"),
    account("6000", "Rent", "expense", "operating_expense"),
    account("6300", "Old Marketing", "expense", "operating_expense", is_active=False),
    account("7000", "Interest Income", "revenue", "other_income"),
    account("7100", "Interest Expense", "expense", "other_income"),
]


def allow_a_subtype_that_no_section_uses(monkeypatch):
    """Imitate a half-finished code change: "other_expense" is accepted by the ledger checks,
    but no section of the statement picks it up. The control total has to notice."""
    import checks

    monkeypatch.setattr(checks, "SUBTYPES", checks.SUBTYPES + ("other_expense",))
    monkeypatch.setitem(
        checks.SUBTYPES_BY_TYPE, "expense", checks.SUBTYPES_BY_TYPE["expense"] + ("other_expense",)
    )
    return CHART + [account("7500", "Bank Fees", "expense", "other_expense")]


def debit(account_number, amount):
    return {"account": account_number, "debit": amount, "credit": "0.00"}


def credit(account_number, amount):
    return {"account": account_number, "debit": "0.00", "credit": amount}


def entry(entry_id, entry_date, *lines, status="posted", memo=""):
    return {"id": entry_id, "date": entry_date, "status": status, "memo": memo, "lines": list(lines)}


def ledger_data(*entries, accounts=CHART):
    return {
        "company": "Test Co",
        "currency": "USD",
        "accounts": list(accounts),
        "journal_entries": list(entries),
    }


def day(text):
    return date.fromisoformat(text)


def statement_of(*entries, start="2026-01-01", end="2026-12-31", accounts=CHART):
    ledger = parse_ledger(ledger_data(*entries, accounts=accounts))
    return income_statement(ledger, day(start), day(end))


def amounts(section):
    return {line.account: line.amount for line in section.lines}


def all_amounts(statement):
    """Every line on the statement, by account number."""
    return {
        **amounts(statement.revenue),
        **amounts(statement.cost_of_goods_sold),
        **amounts(statement.operating_expenses),
        **amounts(statement.other_income),
    }


def every_section(statement):
    """The four sections of the statement, then the balance-sheet accounts."""
    return statement.sections + [statement.balance_sheet_movement]


def detail_of(section, account_number):
    """(entry id, debit, credit, reason) for each line listed under the account. Empty reason means counted."""
    (line,) = [line for line in section.lines if line.account == account_number]
    return [(item.entry_id, item.debit, item.credit, item.reason) for item in line.detail]


def find_errors(data):
    """The blocking errors reported for this data, or an empty list if it loads."""
    try:
        parse_ledger(data)
    except LedgerError as problem:
        return problem.errors
    return []


def error_codes(data):
    return [error["code"] for error in find_errors(data)]
