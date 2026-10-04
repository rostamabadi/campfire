"""Integration tests: the sample ledgers in tests/data, which hold the cases ledger.json does not.

Each file can also be opened in the browser:
    LEDGER_FILE=tests/data/ledger_warnings.json PORT=5002 ./run_server.sh
"""

from collections import Counter
from decimal import Decimal as D
from pathlib import Path

import pytest

from app import create_app
from builders import amounts, day
from ledger import LedgerError, load_ledger
from statement import income_statement

DATA = Path(__file__).parent.parent / "data"
EVERYTHING = "start=2000-01-01&end=2100-12-31"


# --- ledger_blocking_errors.json: every problem that stops the statement ---

def test_blocking_errors_file_reports_every_blocking_code():
    with pytest.raises(LedgerError) as raised:
        load_ledger(DATA / "ledger_blocking_errors.json")

    assert Counter(error["code"] for error in raised.value.errors) == {
        "duplicate_id": 2,           # account 4000 twice, entry JE-101 twice
        "unknown_type": 1,           # account 5000 has type "cost"
        "unknown_subtype": 1,        # account 6100 has subtype "travel"
        "type_subtype_mismatch": 1,  # account 4500: revenue filed as balance_sheet
        "missing_field": 5,          # account 7000, JE-111, a line of JE-112, JE-113, the entry with no id
        "unbalanced_entry": 2,       # JE-102, and JE-106 with its single line
        "unknown_account": 1,        # JE-103 posts to 9999
        "invalid_amount": 5,         # JE-104: text, negative, three decimals, a JSON number, too large
        "invalid_line": 1,           # JE-105 has a line with both sides
        "too_few_lines": 2,          # JE-106 has one line, JE-107 has none
        "unknown_status": 1,         # JE-108 is "pending"
        "invalid_date": 2,           # JE-109 is 2026-02-30, JE-110 is 03/15/2026
    }


def test_blocking_errors_file_shows_the_list_and_no_numbers():
    client = create_app(DATA / "ledger_blocking_errors.json").test_client()

    api_response = client.get(f"/income-statement?{EVERYTHING}")
    page_response = client.get("/")

    assert api_response.status_code == 500
    assert len(api_response.get_json()["errors"]) == 24
    assert page_response.status_code == 500
    assert "JE-102 does not balance: debits 100.00, credits 90.00." in page_response.text
    assert "entry #15 is missing: id." in page_response.text
    assert "Net income" not in page_response.text


# --- ledger_warnings.json: the statement still shows, with notes ---

def test_warnings_file_loads_and_leaves_out_the_broken_drafts_and_voids():
    ledger = load_ledger(DATA / "ledger_warnings.json")

    # 24 entries in the file. 8 draft or void entries have a problem and are left out.
    assert len(ledger.entries) == 16
    assert Counter(warning["code"] for warning in ledger.warnings) == {
        "unbalanced_entry": 2,  # W-021, and W-025 with its single line
        "unknown_account": 1,   # W-022
        "invalid_amount": 1,    # W-023
        "invalid_date": 1,      # W-024
        "too_few_lines": 1,     # W-025
        "duplicate_id": 1,      # the void entry that reuses W-001
        "missing_field": 1,     # W-026
        "invalid_line": 1,      # W-027
    }


def test_warnings_file_statement_by_hand():
    ledger = load_ledger(DATA / "ledger_warnings.json")

    statement = income_statement(ledger, day("2000-01-01"), day("2100-12-31"))

    assert amounts(statement.revenue) == {
        "4000": D("2110.00"),  # W-001 1,000 + W-002 1,000 + W-011 100 + W-012 10
        "4900": D("29.00"),    # credit W-004 80 less debits W-003 50 and W-011 1: positive
    }
    assert amounts(statement.cost_of_goods_sold) == {"5000": D("400.00")}  # W-013, which has no memo
    assert amounts(statement.operating_expenses) == {
        "6000": D("-60.00"),    # W-006 40 less the W-005 credit of 100: a negative expense
        "6300": D("200.10"),    # W-009, inactive account
        "10000": D("5.00"),     # W-010, listed after the four-digit accounts
    }
    assert list(amounts(statement.operating_expenses)) == ["6000", "6300", "10000"]
    assert amounts(statement.other_income) == {
        "7000": D("12.34"),   # W-008. Its void twin W-028 is not counted
        "7100": D("-30.00"),  # W-007, an expense account under other income
    }
    assert statement.gross_profit == D("1739.00")      # 2,139.00 - 400.00
    assert statement.operating_income == D("1593.90")  # 1,739.00 - 145.10
    assert statement.net_income == D("1576.24")        # 1,593.90 - 17.66
    assert statement.balance_sheet_movement.total == D("1576.24")


def test_warnings_file_shows_each_kind_of_note():
    ledger = load_ledger(DATA / "ledger_warnings.json")

    statement = income_statement(ledger, day("2000-01-01"), day("2100-12-31"))
    by_code = {warning["code"]: warning for warning in statement.warnings}

    assert by_code["draft_not_included"]["entry_ids"] == ["W-020"]          # the one sound draft
    assert by_code["possible_duplicate"]["entry_ids"] == ["W-001", "W-002"]  # W-028 is void, so W-008 is not one
    assert len(statement.warnings) == 11  # the 9 ledger warnings and these two


def test_warnings_file_page_shows_the_statement_with_the_notes():
    client = create_app(DATA / "ledger_warnings.json").test_client()

    response = client.get(f"/?{EVERYTHING}")

    assert response.status_code == 200
    assert "1,576.24" in response.text
    assert "(60.00)" in response.text  # the negative rent
    assert "W-021 does not balance: debits 500.00, credits 400.00. This entry is a draft" in response.text
    assert "W-001 and W-002 are posted on 2026-01-05 with identical lines." in response.text


# --- ledger_unreadable.json: the file stops in the middle ---

def test_unreadable_file_is_one_clear_error():
    client = create_app(DATA / "ledger_unreadable.json").test_client()

    response = client.get(f"/income-statement?{EVERYTHING}")

    assert response.status_code == 500
    (error,) = response.get_json()["errors"]
    assert error["code"] == "unreadable_ledger"
    assert error["message"].startswith("The ledger file could not be read:")


# --- choosing the ledger file ---

def test_the_ledger_file_can_be_chosen_with_an_environment_variable(monkeypatch):
    monkeypatch.setenv("LEDGER_FILE", str(DATA / "ledger_warnings.json"))

    response = create_app().test_client().get(f"/income-statement?{EVERYTHING}")

    assert response.get_json()["company"] == "Warnings and Edge Cases Co"
