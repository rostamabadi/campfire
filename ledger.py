"""The ledger as plain dataclasses, and loading it from the JSON file.

The checks on the raw data live in checks.py. Money is parsed straight from the JSON strings
into Decimal. It never passes through float.
"""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from checks import find_account_errors, find_entry_problems, parse_amount, parse_date, problem


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
    warnings: list[dict]  # problems in draft and void entries, which were left out


class LedgerError(Exception):
    """The ledger data has problems. `errors` lists every one that was found."""

    def __init__(self, errors: list[dict]):
        super().__init__(f"{len(errors)} problem(s) in the ledger")
        self.errors = errors


def build_entry(raw: dict) -> Entry:
    """Build an Entry from raw data that has passed the checks. The memo is optional."""
    lines = [
        Line(
            account=raw_line["account"],
            debit=parse_amount(raw_line["debit"]),
            credit=parse_amount(raw_line["credit"]),
        )
        for raw_line in raw["lines"]
    ]
    return Entry(
        id=raw["id"],
        date=parse_date(raw["date"]),
        status=raw["status"],
        memo=raw.get("memo", ""),
        lines=lines,
    )


def parse_ledger(data: dict) -> Ledger:
    """Build a Ledger from the parsed JSON. Raises LedgerError listing every blocking problem.

    A problem blocks the statement when it could change the totals: any problem in the chart
    of accounts, in a posted entry, or in an entry whose status cannot be read. A draft or
    void entry never reaches the totals, so its problems become warnings and the entry is
    left out.
    """
    errors = find_account_errors(data["accounts"])
    account_numbers = {raw["number"] for raw in data["accounts"] if "number" in raw}

    warnings = []
    entries = []
    seen_ids = set()
    for position, raw in enumerate(data["journal_entries"], start=1):
        problems = find_entry_problems(raw, position, account_numbers, seen_ids)
        if "id" in raw:
            seen_ids.add(raw["id"])

        if not problems:
            entries.append(build_entry(raw))
        elif raw.get("status") in ("draft", "void"):
            kind = "a draft" if raw["status"] == "draft" else "void"
            for found in problems:
                found["message"] += f" This entry is {kind}, so the totals are not affected."
            warnings.extend(problems)
        else:
            errors.extend(problems)

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

    return Ledger(
        company=data["company"],
        currency=data["currency"],
        accounts=accounts,
        entries=entries,
        warnings=warnings,
    )


def load_ledger(path) -> Ledger:
    """Read and check the ledger file. Raises LedgerError if it is unreadable or has problems."""
    try:
        with open(path) as file:
            return parse_ledger(json.load(file))
    except KeyError as missing:
        message = f"The ledger file is missing the field {missing}."
    except (OSError, ValueError, TypeError, AttributeError) as failure:  # no file, not JSON, wrong structure
        message = f"The ledger file could not be read: {failure}"
    raise LedgerError([problem("unreadable_ledger", message)])
