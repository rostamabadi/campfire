"""Check the ledger data and load it into plain dataclasses.

Money is parsed straight from the JSON strings into Decimal. It never passes through float.
"""

import json
import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Account:
    number: str
    name: str
    type: str
    subtype: str
    is_active: bool


@dataclass(frozen=True)
class Line:
    account: str  # account number
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class Entry:
    id: str
    date: date
    status: str
    memo: str
    lines: list[Line]


@dataclass(frozen=True)
class Ledger:
    company: str
    currency: str
    accounts: dict[str, Account]  # keyed by account number
    entries: list[Entry]


class LedgerError(Exception):
    """The ledger data has problems. `errors` lists every one that was found."""

    def __init__(self, errors: list[dict]):
        super().__init__(f"{len(errors)} problem(s) in the ledger")
        self.errors = errors


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
    more, with at most two decimal places.
    """
    if not isinstance(text, str):
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        return None
    return amount


def find_errors(data: dict) -> list[dict]:
    """Every problem in the raw ledger data. An empty list means the data is sound."""
    errors = []

    account_numbers = set()
    for raw in data["accounts"]:
        number = raw["number"]
        if number in account_numbers:
            errors.append({
                "code": "duplicate_id",
                "account": number,
                "message": f"Account number {number} is used by more than one account.",
            })
        account_numbers.add(number)

        account_type = raw["type"]
        subtype = raw["subtype"]
        if account_type not in SUBTYPES_BY_TYPE:
            errors.append({
                "code": "unknown_type",
                "account": number,
                "message": f"Account {number} ({raw['name']}) has type '{account_type}'. "
                           f"Expected one of: {', '.join(SUBTYPES_BY_TYPE)}.",
            })
        if subtype not in SUBTYPES:
            errors.append({
                "code": "unknown_subtype",
                "account": number,
                "message": f"Account {number} ({raw['name']}) has subtype '{subtype}'. "
                           f"Expected one of: {', '.join(SUBTYPES)}.",
            })
        if account_type in SUBTYPES_BY_TYPE and subtype in SUBTYPES:
            allowed = SUBTYPES_BY_TYPE[account_type]
            if subtype not in allowed:
                errors.append({
                    "code": "type_subtype_mismatch",
                    "account": number,
                    "message": f"Account {number} ({raw['name']}) has type '{account_type}' and subtype "
                               f"'{subtype}', which do not go together. "
                               f"For type '{account_type}' the subtype must be one of: {', '.join(allowed)}.",
                })

    entry_ids = set()
    for raw in data["journal_entries"]:
        entry_id = raw["id"]
        if entry_id in entry_ids:
            errors.append({
                "code": "duplicate_id",
                "entry_id": entry_id,
                "message": f"Entry id {entry_id} is used by more than one journal entry.",
            })
        entry_ids.add(entry_id)
        if raw["status"] not in STATUSES:
            errors.append({
                "code": "unknown_status",
                "entry_id": entry_id,
                "message": f"{entry_id} has status '{raw['status']}'. "
                           f"Expected one of: {', '.join(STATUSES)}.",
            })
        if parse_date(raw["date"]) is None:
            errors.append({
                "code": "invalid_date",
                "entry_id": entry_id,
                "message": f"{entry_id} has date '{raw['date']}', which is not a valid YYYY-MM-DD date.",
            })
        errors.extend(find_line_errors(entry_id, raw["lines"], account_numbers))

    return errors


def find_line_errors(entry_id: str, lines: list[dict], account_numbers: set[str]) -> list[dict]:
    """Problems in one entry's lines, including whether the entry balances."""
    errors = []
    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")
    amounts_are_valid = True

    for raw in lines:
        account = raw["account"]
        if account not in account_numbers:
            errors.append({
                "code": "unknown_account",
                "entry_id": entry_id,
                "message": f"{entry_id} posts to account {account}, which is not in the chart of accounts.",
            })

        debit = parse_amount(raw["debit"])
        credit = parse_amount(raw["credit"])
        if debit is None or credit is None:
            amounts_are_valid = False
            errors.append({
                "code": "invalid_amount",
                "entry_id": entry_id,
                "message": f"{entry_id} has a line on account {account} with debit {raw['debit']!r} and "
                           f"credit {raw['credit']!r}. Amounts must be decimal strings, zero or more, "
                           f"with at most two decimal places.",
            })
            continue

        if debit != 0 and credit != 0:
            errors.append({
                "code": "invalid_line",
                "entry_id": entry_id,
                "message": f"{entry_id} has a line on account {account} with both a debit ({debit:,.2f}) "
                           f"and a credit ({credit:,.2f}). A line is one or the other.",
            })
        total_debits += debit
        total_credits += credit

    # The balance check only means something when every amount could be read.
    if amounts_are_valid and total_debits != total_credits:
        errors.append({
            "code": "unbalanced_entry",
            "entry_id": entry_id,
            "message": f"{entry_id} does not balance: debits {total_debits:,.2f}, credits {total_credits:,.2f}.",
        })

    return errors


def parse_ledger(data: dict) -> Ledger:
    """Build a Ledger from the parsed JSON. Raises LedgerError listing every problem found."""
    errors = find_errors(data)
    if errors:
        raise LedgerError(errors)

    accounts = {}
    for raw in data["accounts"]:
        accounts[raw["number"]] = Account(
            number=raw["number"],
            name=raw["name"],
            type=raw["type"],
            subtype=raw["subtype"],
            is_active=raw["is_active"],
        )

    entries = []
    for raw in data["journal_entries"]:
        lines = [
            Line(
                account=raw_line["account"],
                debit=parse_amount(raw_line["debit"]),
                credit=parse_amount(raw_line["credit"]),
            )
            for raw_line in raw["lines"]
        ]
        entries.append(Entry(
            id=raw["id"],
            date=parse_date(raw["date"]),
            status=raw["status"],
            memo=raw["memo"],
            lines=lines,
        ))

    return Ledger(company=data["company"], currency=data["currency"], accounts=accounts, entries=entries)


def load_ledger(path) -> Ledger:
    """Read and check the ledger file. Raises LedgerError if it is unreadable or has problems."""
    try:
        with open(path) as file:
            return parse_ledger(json.load(file))
    except KeyError as missing:
        message = f"The ledger file is missing the field {missing}."
    except (OSError, ValueError, TypeError) as problem:  # no file, not JSON, wrong structure
        message = f"The ledger file could not be read: {problem}"
    raise LedgerError([{"code": "unreadable_ledger", "message": message}])
