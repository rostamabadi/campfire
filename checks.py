"""The checks on the raw ledger data, before any of it is loaded.

Everything here works on the plain dictionaries read from the JSON file. A check returns a
list of problems. Each problem is a dictionary with a code, where it was found, and a
message written for an accountant.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

STATUSES = ("posted", "draft", "void")
SUBTYPES = (
    "operating_revenue",
    "contra_revenue",
    "cogs",
    "operating_expense",
    "other_income",
    "balance_sheet",
)
# The subtypes each account type may have. Anything else would put an account on the wrong
# statement, or on none, without the totals looking wrong.
SUBTYPES_BY_TYPE = {
    "asset": ("balance_sheet",),
    "liability": ("balance_sheet",),
    "equity": ("balance_sheet",),
    "revenue": ("operating_revenue", "contra_revenue", "other_income"),
    "expense": ("cogs", "operating_expense", "other_income"),
}
# Decimal sums are exact up to 28 significant digits. Every amount must be below this limit,
# which keeps any total far away from that, so nothing is ever rounded.
AMOUNT_LIMIT = Decimal("1000000000000000")


def problem(code: str, message: str, **where) -> dict:
    """One problem: a code, where it is (such as entry_id="JE-001"), and a message."""
    return {"code": code, **where, "message": message}


def parse_date(text) -> date | None:
    """Return the date for a strict YYYY-MM-DD string, or None if it is not one."""
    if not isinstance(text, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:  # the right shape but not a real date, such as 2026-02-30
        return None


def parse_amount(text) -> Decimal | None:
    """Return the amount for a decimal string, or None if it is not valid money.

    Valid money is a string (a JSON number would already have become a float), zero or
    more, below AMOUNT_LIMIT, with at most two decimal places.
    """
    if not isinstance(text, str):
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0 or amount >= AMOUNT_LIMIT:
        return None
    if amount.as_tuple().exponent < -2:
        return None
    return amount


def find_account_errors(raw_accounts: list[dict]) -> list[dict]:
    """Every problem in the chart of accounts. These always block the statement."""
    errors = []
    numbers = set()

    for position, raw in enumerate(raw_accounts, start=1):
        number = raw.get("number", f"#{position}")
        missing = [field for field in ("number", "name", "type", "subtype", "is_active") if field not in raw]
        if missing:
            errors.append(problem(
                "missing_field", f"Account {number} is missing: {', '.join(missing)}.", account=number,
            ))
            continue

        if number in numbers:
            errors.append(problem(
                "duplicate_id", f"Account number {number} is used by more than one account.", account=number,
            ))
        numbers.add(number)

        name = raw["name"]
        account_type = raw["type"]
        subtype = raw["subtype"]
        if account_type not in SUBTYPES_BY_TYPE:
            errors.append(problem(
                "unknown_type",
                f"Account {number} ({name}) has type '{account_type}'. "
                f"Expected one of: {', '.join(SUBTYPES_BY_TYPE)}.",
                account=number,
            ))
        if subtype not in SUBTYPES:
            errors.append(problem(
                "unknown_subtype",
                f"Account {number} ({name}) has subtype '{subtype}'. Expected one of: {', '.join(SUBTYPES)}.",
                account=number,
            ))
        if account_type in SUBTYPES_BY_TYPE and subtype in SUBTYPES:
            allowed = SUBTYPES_BY_TYPE[account_type]
            if subtype not in allowed:
                errors.append(problem(
                    "type_subtype_mismatch",
                    f"Account {number} ({name}) has type '{account_type}' and subtype '{subtype}', "
                    f"which do not go together. "
                    f"For type '{account_type}' the subtype must be one of: {', '.join(allowed)}.",
                    account=number,
                ))

    return errors


def find_entry_problems(raw: dict, position: int, account_numbers: set[str], seen_ids: set[str]) -> list[dict]:
    """Every problem in one raw journal entry. An empty list means the entry is sound."""
    entry_id = raw.get("id", f"entry #{position}")
    missing = [field for field in ("id", "date", "status", "lines") if field not in raw]
    if missing:
        return [problem("missing_field", f"{entry_id} is missing: {', '.join(missing)}.", entry_id=entry_id)]

    problems = []
    if entry_id in seen_ids:
        problems.append(problem(
            "duplicate_id", f"Entry id {entry_id} is used by more than one journal entry.", entry_id=entry_id,
        ))
    if raw["status"] not in STATUSES:
        problems.append(problem(
            "unknown_status",
            f"{entry_id} has status '{raw['status']}'. Expected one of: {', '.join(STATUSES)}.",
            entry_id=entry_id,
        ))
    if parse_date(raw["date"]) is None:
        problems.append(problem(
            "invalid_date",
            f"{entry_id} has date '{raw['date']}', which is not a valid YYYY-MM-DD date.",
            entry_id=entry_id,
        ))
    problems.extend(find_line_problems(entry_id, raw["lines"], account_numbers))
    return problems


def find_line_problems(entry_id: str, lines: list[dict], account_numbers: set[str]) -> list[dict]:
    """Problems in one entry's lines, including whether the entry balances."""
    problems = []
    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")
    amounts_are_valid = True

    if len(lines) < 2:
        count = "1 line" if len(lines) == 1 else "no lines"
        problems.append(problem(
            "too_few_lines", f"{entry_id} has {count}. A journal entry needs at least two.", entry_id=entry_id,
        ))

    for raw in lines:
        missing = [field for field in ("account", "debit", "credit") if field not in raw]
        if missing:
            amounts_are_valid = False
            problems.append(problem(
                "missing_field", f"{entry_id} has a line that is missing: {', '.join(missing)}.", entry_id=entry_id,
            ))
            continue

        account = raw["account"]
        if account not in account_numbers:
            problems.append(problem(
                "unknown_account",
                f"{entry_id} posts to account {account}, which is not in the chart of accounts.",
                entry_id=entry_id,
            ))

        debit = parse_amount(raw["debit"])
        credit = parse_amount(raw["credit"])
        if debit is None or credit is None:
            amounts_are_valid = False
            problems.append(problem(
                "invalid_amount",
                f"{entry_id} has a line on account {account} with debit {raw['debit']!r} and "
                f"credit {raw['credit']!r}. Amounts must be decimal strings, zero or more, "
                f"with at most two decimal places and at most 15 digits before the point.",
                entry_id=entry_id,
            ))
            continue

        if debit != 0 and credit != 0:
            problems.append(problem(
                "invalid_line",
                f"{entry_id} has a line on account {account} with both a debit ({debit:,.2f}) "
                f"and a credit ({credit:,.2f}). A line is one or the other.",
                entry_id=entry_id,
            ))
        total_debits += debit
        total_credits += credit

    # The balance check only means something when every amount could be read.
    if amounts_are_valid and total_debits != total_credits:
        problems.append(problem(
            "unbalanced_entry",
            f"{entry_id} does not balance: debits {total_debits:,.2f}, credits {total_credits:,.2f}.",
            entry_id=entry_id,
        ))

    return problems
