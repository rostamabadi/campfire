"""Integration tests: reading the ledger from a file on disk."""

import json
from datetime import date
from decimal import Decimal

import pytest

from builders import LEDGER_PATH, credit, debit, entry, ledger_data
from ledger import LedgerError, load_ledger


def test_the_real_ledger_loads_without_errors():
    ledger = load_ledger(LEDGER_PATH)

    assert ledger.company == "Northwind Coffee Roasters"
    assert ledger.currency == "USD"
    assert len(ledger.accounts) == 15
    assert len(ledger.entries) == 25


def test_amounts_load_as_decimal_and_dates_as_date():
    ledger = load_ledger(LEDGER_PATH)
    january_sales = ledger.entries[1]

    assert january_sales.id == "JE-002"
    assert january_sales.date == date(2026, 1, 5)
    assert january_sales.lines[0].debit == Decimal("12450.75")
    assert type(january_sales.lines[0].debit) is Decimal
    assert type(january_sales.lines[0].credit) is Decimal


def unreadable_message(path):
    with pytest.raises(LedgerError) as raised:
        load_ledger(path)
    (error,) = raised.value.errors
    assert error["code"] == "unreadable_ledger"
    return error["message"]


def test_missing_file(tmp_path):
    assert "could not be read" in unreadable_message(tmp_path / "nothing-here.json")


def test_file_that_is_not_json(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text("{not json")

    assert "could not be read" in unreadable_message(path)


def test_file_without_a_top_level_field(tmp_path):
    data = ledger_data(entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")))
    del data["journal_entries"]
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(data))

    assert "missing the field 'journal_entries'" in unreadable_message(path)


def test_file_with_the_wrong_structure(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"company": "Test Co", "currency": "USD", "accounts": ["oops"], "journal_entries": []}))

    assert "could not be read" in unreadable_message(path)
