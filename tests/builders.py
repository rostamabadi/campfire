"""Helpers for building small ledgers in tests, in the same shape as ledger.json."""


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
