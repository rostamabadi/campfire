"""The ledger loader: the real file loads, and each kind of bad data is reported."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from builders import CHART, account, credit, debit, entry, ledger_data
from ledger import LedgerError, find_errors, load_ledger, parse_amount, parse_date, parse_ledger

LEDGER_PATH = Path(__file__).parent.parent / "ledger.json"


def error_codes(data):
    return [error["code"] for error in find_errors(data)]


# --- the real file ---

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


# --- parsing single values ---

@pytest.mark.parametrize("text", ["0.00", "12450.75", "5000", "0.1"])
def test_valid_amounts(text):
    assert parse_amount(text) == Decimal(text)


@pytest.mark.parametrize("value", ["abc", "", "-5.00", "1.005", "NaN", "Infinity", 100.0, 100, None])
def test_invalid_amounts(value):
    assert parse_amount(value) is None


def test_valid_date():
    assert parse_date("2026-01-31") == date(2026, 1, 31)


@pytest.mark.parametrize("value", ["2026-02-30", "01/31/2026", "2026-1-5", "20260105", "2026-01-05T00:00", "", None])
def test_invalid_dates(value):
    assert parse_date(value) is None


# --- checks on the data ---

def test_a_sound_ledger_has_no_errors():
    data = ledger_data(entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")))

    assert find_errors(data) == []


def test_unbalanced_entry():
    data = ledger_data(entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "90.00")))

    errors = find_errors(data)

    assert [error["code"] for error in errors] == ["unbalanced_entry"]
    assert errors[0]["entry_id"] == "JE-1"
    assert "debits 100.00, credits 90.00" in errors[0]["message"]


def test_an_unbalanced_draft_is_still_an_error():
    data = ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "90.00"), status="draft")
    )

    assert error_codes(data) == ["unbalanced_entry"]


def test_unknown_account():
    data = ledger_data(entry("JE-1", "2026-01-05", debit("9999", "100.00"), credit("4000", "100.00")))

    errors = find_errors(data)

    assert [error["code"] for error in errors] == ["unknown_account"]
    assert "9999" in errors[0]["message"]


@pytest.mark.parametrize("bad_amount", ["abc", "-100.00", "100.005", 100.0])
def test_invalid_amount_is_reported_once_without_a_balance_error(bad_amount):
    data = ledger_data(entry("JE-1", "2026-01-05", debit("1100", bad_amount), credit("4000", "100.00")))

    assert error_codes(data) == ["invalid_amount"]


def test_line_with_both_a_debit_and_a_credit():
    both_sides = {"account": "1100", "debit": "100.00", "credit": "100.00"}
    data = ledger_data(entry("JE-1", "2026-01-05", both_sides))

    assert error_codes(data) == ["invalid_line"]


def test_unknown_status():
    data = ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00"), status="pending")
    )

    assert error_codes(data) == ["unknown_status"]


def test_unknown_subtype():
    accounts = CHART + [account("8000", "Mystery", "expense", "sundry")]

    errors = find_errors(ledger_data(accounts=accounts))

    assert [error["code"] for error in errors] == ["unknown_subtype"]
    assert errors[0]["account"] == "8000"


def test_invalid_entry_date():
    data = ledger_data(entry("JE-1", "2026-02-30", debit("1100", "100.00"), credit("4000", "100.00")))

    assert error_codes(data) == ["invalid_date"]


def test_duplicate_entry_id():
    data = ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
        entry("JE-1", "2026-02-05", debit("1100", "250.00"), credit("4000", "250.00")),
    )

    errors = find_errors(data)

    assert [error["code"] for error in errors] == ["duplicate_id"]
    assert errors[0]["entry_id"] == "JE-1"


def test_duplicate_account_number():
    accounts = CHART + [account("4000", "Sales Again", "revenue", "operating_revenue")]

    errors = find_errors(ledger_data(accounts=accounts))

    assert [error["code"] for error in errors] == ["duplicate_id"]
    assert errors[0]["account"] == "4000"


def test_every_problem_is_reported_not_only_the_first():
    data = ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "90.00")),
        entry("JE-2", "2026-01-06", debit("9999", "50.00"), credit("4000", "50.00"), status="pending"),
    )

    errors = find_errors(data)

    assert [(error["entry_id"], error["code"]) for error in errors] == [
        ("JE-1", "unbalanced_entry"),
        ("JE-2", "unknown_status"),
        ("JE-2", "unknown_account"),
    ]


def test_parse_ledger_raises_with_the_full_list():
    data = ledger_data(entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "90.00")))

    with pytest.raises(LedgerError) as raised:
        parse_ledger(data)

    assert [error["code"] for error in raised.value.errors] == ["unbalanced_entry"]


# --- files that cannot be read at all ---

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


def test_file_with_a_missing_field(tmp_path):
    data = ledger_data(entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")))
    del data["journal_entries"][0]["lines"]
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(data))

    assert "missing the field 'lines'" in unreadable_message(path)
