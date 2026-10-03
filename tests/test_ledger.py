"""The ledger loader: the real file loads, and each kind of bad data is reported."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from builders import CHART, account, credit, debit, entry, ledger_data
from ledger import LedgerError, load_ledger, parse_amount, parse_date, parse_ledger

LEDGER_PATH = Path(__file__).parent.parent / "ledger.json"


def find_errors(data):
    """The blocking errors reported for this data, or an empty list if it loads."""
    try:
        parse_ledger(data)
    except LedgerError as problem:
        return problem.errors
    return []


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

@pytest.mark.parametrize("text", ["0.00", "12450.75", "5000", "0.1", "999999999999999.99"])
def test_valid_amounts(text):
    assert parse_amount(text) == Decimal(text)


@pytest.mark.parametrize(
    "value",
    ["abc", "", "-5.00", "1.005", "NaN", "Infinity", "1000000000000000.00", 100.0, 100, None],
)
def test_invalid_amounts(value):
    assert parse_amount(value) is None


def test_the_largest_amounts_still_add_up_exactly():
    # Sums are exact up to 28 significant digits. The amount limit keeps totals far below that.
    largest = parse_amount("999999999999999.99")

    assert largest + largest + Decimal("0.01") == Decimal("1999999999999999.99")


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


# --- problems in draft and void entries cannot change the totals, so they only warn ---

@pytest.mark.parametrize("status, wording", [("draft", "This entry is a draft"), ("void", "This entry is void")])
def test_a_problem_in_a_draft_or_void_entry_is_a_warning_and_the_entry_is_left_out(status, wording):
    data = ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "50.00"), credit("4000", "50.00")),
        entry("JE-2", "2026-01-06", debit("1100", "100.00"), credit("4000", "90.00"), status=status),
    )

    ledger = parse_ledger(data)  # does not raise

    assert [entry_.id for entry_ in ledger.entries] == ["JE-1"]
    (warning,) = ledger.warnings
    assert warning["code"] == "unbalanced_entry"
    assert warning["entry_id"] == "JE-2"
    assert warning["message"] == (
        f"JE-2 does not balance: debits 100.00, credits 90.00. {wording}, so the totals are not affected."
    )


def test_the_same_problem_in_a_posted_entry_blocks():
    data = ledger_data(
        entry("JE-2", "2026-01-06", debit("1100", "100.00"), credit("4000", "90.00"), status="posted"),
    )

    assert error_codes(data) == ["unbalanced_entry"]


def test_a_void_entry_that_reuses_an_id_is_a_warning():
    data = ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "50.00"), credit("4000", "50.00")),
        entry("JE-1", "2026-01-05", debit("1100", "50.00"), credit("4000", "50.00"), status="void"),
    )

    ledger = parse_ledger(data)

    assert [warning["code"] for warning in ledger.warnings] == ["duplicate_id"]
    assert len(ledger.entries) == 1


def test_a_sound_draft_is_loaded_without_warnings():
    data = ledger_data(
        entry("JE-1", "2026-01-05", debit("6000", "50.00"), credit("2000", "50.00"), status="draft"),
    )

    ledger = parse_ledger(data)

    assert [entry_.id for entry_ in ledger.entries] == ["JE-1"]
    assert ledger.warnings == []


# --- missing fields ---

def test_a_posted_entry_with_a_missing_field_is_named():
    data = ledger_data(entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")))
    del data["journal_entries"][0]["date"]
    del data["journal_entries"][0]["lines"]

    errors = find_errors(data)

    assert errors == [{"code": "missing_field", "entry_id": "JE-1", "message": "JE-1 is missing: date, lines."}]


def test_an_entry_without_an_id_is_named_by_its_position():
    data = ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
        entry("JE-2", "2026-01-06", debit("1100", "100.00"), credit("4000", "100.00")),
    )
    del data["journal_entries"][1]["id"]

    errors = find_errors(data)

    assert [error["message"] for error in errors] == ["entry #2 is missing: id."]


def test_a_line_with_a_missing_field():
    data = ledger_data(entry("JE-1", "2026-01-05", {"account": "1100", "debit": "100.00"}, credit("4000", "100.00")))

    errors = find_errors(data)

    assert [error["code"] for error in errors] == ["missing_field"]
    assert errors[0]["message"] == "JE-1 has a line that is missing: credit."


def test_an_account_with_a_missing_field():
    accounts = CHART + [{"number": "8000", "name": "Half an account"}]

    errors = find_errors(ledger_data(accounts=accounts))

    assert errors == [{
        "code": "missing_field",
        "account": "8000",
        "message": "Account 8000 is missing: type, subtype, is_active.",
    }]


def test_the_memo_is_optional():
    data = ledger_data(entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")))
    del data["journal_entries"][0]["memo"]

    ledger = parse_ledger(data)

    assert ledger.entries[0].memo == ""


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
    data = ledger_data(
        entry("JE-1", "2026-01-05", both_sides, debit("1100", "50.00"), credit("4000", "50.00"))
    )

    assert error_codes(data) == ["invalid_line"]


def test_an_entry_with_no_lines():
    errors = find_errors(ledger_data(entry("JE-1", "2026-01-05")))

    assert [error["code"] for error in errors] == ["too_few_lines"]
    assert errors[0]["message"] == "JE-1 has no lines. A journal entry needs at least two."


def test_an_entry_with_one_line_has_too_few_lines_and_cannot_balance():
    errors = find_errors(ledger_data(entry("JE-1", "2026-01-05", debit("1100", "100.00"))))

    assert [error["code"] for error in errors] == ["too_few_lines", "unbalanced_entry"]
    assert errors[0]["message"] == "JE-1 has 1 line. A journal entry needs at least two."


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


@pytest.mark.parametrize(
    "account_type, subtype",
    [
        ("revenue", "balance_sheet"),      # would drop off the income statement
        ("asset", "operating_expense"),    # would appear on it
        ("expense", "operating_revenue"),
        ("revenue", "cogs"),
    ],
)
def test_account_type_and_subtype_must_agree(account_type, subtype):
    accounts = CHART + [account("8000", "Misfiled", account_type, subtype)]

    errors = find_errors(ledger_data(accounts=accounts))

    assert [error["code"] for error in errors] == ["type_subtype_mismatch"]
    assert errors[0]["account"] == "8000"
    assert f"type '{account_type}' and subtype '{subtype}'" in errors[0]["message"]


def test_unknown_account_type():
    accounts = CHART + [account("8000", "Mystery", "income", "operating_revenue")]

    errors = find_errors(ledger_data(accounts=accounts))

    assert [error["code"] for error in errors] == ["unknown_type"]
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
