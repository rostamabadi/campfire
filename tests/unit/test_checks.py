"""Unit tests: each check on the raw ledger data, on small ledgers built inside the test."""

import pytest

from builders import CHART, account, credit, debit, entry, error_codes, find_errors, ledger_data
from ledger import LedgerError, parse_ledger


def test_a_sound_ledger_has_no_errors():
    data = ledger_data(entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")))

    assert find_errors(data) == []


def test_unbalanced_entry():
    data = ledger_data(entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "90.00")))

    errors = find_errors(data)

    assert [error["code"] for error in errors] == ["unbalanced_entry"]
    assert errors[0]["entry_id"] == "JE-1"
    assert "debits 100.00, credits 90.00" in errors[0]["message"]


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
