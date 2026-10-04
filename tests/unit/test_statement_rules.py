"""Unit tests: the rules of the statement, one small ledger per rule."""

from decimal import Decimal as D

import pytest

from builders import (
    CHART,
    account,
    all_amounts,
    allow_a_subtype_that_no_section_uses,
    amounts,
    credit,
    day,
    debit,
    entry,
    ledger_data,
    statement_of,
)
from ledger import parse_ledger
from statement import ControlTotalError, posted_date_span


def test_the_control_total_stops_a_statement_that_leaves_an_account_out(monkeypatch):
    accounts = allow_a_subtype_that_no_section_uses(monkeypatch)

    with pytest.raises(ControlTotalError) as raised:
        statement_of(
            entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
            entry("JE-2", "2026-01-06", debit("7500", "30.00"), credit("1000", "30.00")),
            accounts=accounts,
        )

    # The statement sees only the 100.00 of sales. The balance sheet side moved by 100.00 - 30.00.
    assert raised.value.error == {
        "code": "control_total_mismatch",
        "message": "For 2026-01-01 to 2026-12-31, net income is 100.00 but the balance-sheet "
                   "accounts moved by 70.00. These must be equal, so the statement is not shown.",
    }


def test_subtotals_follow_the_statement_formulas():
    statement = statement_of(
        entry("JE-1", "2026-01-05", debit("1100", "1000.00"), credit("4000", "1000.00")),
        entry("JE-2", "2026-01-06", debit("4900", "100.00"), credit("1100", "100.00")),
        entry("JE-3", "2026-01-07", debit("5000", "300.00"), credit("1000", "300.00")),
        entry("JE-4", "2026-01-08", debit("6000", "200.00"), credit("1000", "200.00")),
        entry("JE-5", "2026-01-09", debit("1000", "50.00"), credit("7000", "50.00")),
    )

    assert statement.revenue.total == D("900.00")      # 1,000 - 100
    assert statement.gross_profit == D("600.00")       # 900 - 300
    assert statement.operating_income == D("400.00")   # 600 - 200
    assert statement.net_income == D("450.00")         # 400 + 50


def test_void_and_draft_entries_are_not_counted():
    statement = statement_of(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
        entry("JE-2", "2026-01-05", debit("1100", "40.00"), credit("4000", "40.00"), status="void"),
        entry("JE-3", "2026-01-05", debit("6000", "30.00"), credit("2000", "30.00"), status="draft"),
    )

    assert amounts(statement.revenue)["4000"] == D("100.00")
    assert amounts(statement.operating_expenses)["6000"] == D("0.00")
    assert statement.net_income == D("100.00")


def test_an_inactive_account_still_reports_its_history():
    statement = statement_of(
        entry("JE-1", "2026-01-20", debit("6300", "2500.10"), credit("2000", "2500.10")),
    )

    assert amounts(statement.operating_expenses)["6300"] == D("2500.10")
    assert statement.net_income == D("-2500.10")


def test_a_credit_to_an_expense_account_reduces_the_expense():
    statement = statement_of(
        entry("JE-1", "2026-03-10", debit("6000", "1199.97"), credit("2000", "1199.97")),
        entry("JE-2", "2026-03-20", debit("2000", "100.00"), credit("6000", "100.00")),
    )

    assert amounts(statement.operating_expenses)["6000"] == D("1099.97")


def test_an_expense_with_more_credit_than_debit_is_negative_and_raises_net_income():
    statement = statement_of(
        entry("JE-1", "2026-03-20", debit("2000", "100.00"), credit("6000", "100.00")),
    )

    assert amounts(statement.operating_expenses)["6000"] == D("-100.00")
    assert statement.net_income == D("100.00")


def test_contra_revenue_is_a_negative_line_that_reduces_net_revenue():
    statement = statement_of(
        entry("JE-1", "2026-02-03", debit("1100", "1000.00"), credit("4000", "1000.00")),
        entry("JE-2", "2026-02-14", debit("4900", "150.25"), credit("1100", "150.25")),
    )

    assert amounts(statement.revenue) == {"4000": D("1000.00"), "4900": D("-150.25")}
    assert statement.revenue.total == D("849.75")


def test_contra_revenue_with_more_credit_than_debit_is_positive():
    # A return of 150.00 that is reversed by 200.00: the sign comes from the arithmetic, not the subtype.
    statement = statement_of(
        entry("JE-1", "2026-02-14", debit("4900", "150.00"), credit("1100", "150.00")),
        entry("JE-2", "2026-02-20", debit("1100", "200.00"), credit("4900", "200.00")),
    )

    assert amounts(statement.revenue)["4900"] == D("50.00")


def test_a_debit_to_a_revenue_account_reduces_revenue():
    statement = statement_of(
        entry("JE-1", "2026-02-03", debit("1100", "1000.00"), credit("4000", "1000.00")),
        entry("JE-2", "2026-02-04", debit("4000", "250.00"), credit("1100", "250.00")),
    )

    assert amounts(statement.revenue)["4000"] == D("750.00")


def test_section_comes_from_subtype_not_type():
    # 7000 has type "revenue" but subtype "other_income": it belongs below operating income.
    statement = statement_of(
        entry("JE-1", "2026-03-31", debit("1000", "42.18"), credit("7000", "42.18")),
    )

    assert statement.revenue.total == D("0.00")
    assert statement.operating_income == D("0.00")
    assert amounts(statement.other_income)["7000"] == D("42.18")
    assert statement.net_income == D("42.18")


def test_an_expense_in_other_income_is_negative_there():
    # 7100 has type "expense" and subtype "other_income". The section's formula sets the sign.
    statement = statement_of(
        entry("JE-1", "2026-03-31", debit("7100", "30.00"), credit("1000", "30.00")),
    )

    assert amounts(statement.other_income)["7100"] == D("-30.00")
    assert statement.net_income == D("-30.00")


def test_entries_that_touch_only_the_balance_sheet_change_nothing():
    statement = statement_of(
        entry("JE-1", "2026-01-10", debit("1100", "12000.00"), credit("2000", "12000.00")),
        entry("JE-2", "2026-02-15", debit("1000", "12000.00"), credit("1100", "12000.00")),
    )

    assert set(all_amounts(statement).values()) == {D("0.00")}
    assert statement.net_income == D("0.00")


def test_an_entry_with_three_lines():
    statement = statement_of(
        entry(
            "JE-1", "2026-03-02",
            debit("1100", "14850.00"), debit("4900", "150.00"), credit("4000", "15000.00"),
        ),
    )

    assert amounts(statement.revenue) == {"4000": D("15000.00"), "4900": D("-150.00")}
    assert statement.revenue.total == D("14850.00")


def test_both_ends_of_the_range_are_included():
    statement = statement_of(
        entry("JE-1", "2026-01-31", debit("1100", "1.00"), credit("4000", "1.00")),      # day before
        entry("JE-2", "2026-02-01", debit("1100", "10.00"), credit("4000", "10.00")),    # first day
        entry("JE-3", "2026-02-28", debit("1100", "100.00"), credit("4000", "100.00")),  # last day
        entry("JE-4", "2026-03-01", debit("1100", "1000.00"), credit("4000", "1000.00")),  # day after
        start="2026-02-01",
        end="2026-02-28",
    )

    assert statement.revenue.total == D("110.00")


def test_a_one_day_range():
    statement = statement_of(
        entry("JE-1", "2026-02-01", debit("1100", "10.00"), credit("4000", "10.00")),
        entry("JE-2", "2026-02-02", debit("1100", "100.00"), credit("4000", "100.00")),
        start="2026-02-01",
        end="2026-02-01",
    )

    assert statement.revenue.total == D("10.00")


def test_entries_do_not_need_to_be_in_date_order():
    statement = statement_of(
        entry("JE-1", "2026-03-01", debit("1100", "1000.00"), credit("4000", "1000.00")),
        entry("JE-2", "2026-02-28", debit("1100", "100.00"), credit("4000", "100.00")),
        entry("JE-3", "2026-01-31", debit("1100", "1.00"), credit("4000", "1.00")),
        entry("JE-4", "2026-02-01", debit("1100", "10.00"), credit("4000", "10.00")),
        start="2026-02-01",
        end="2026-02-28",
    )

    assert statement.revenue.total == D("110.00")


def test_revenue_lists_operating_revenue_first_then_contra_each_by_account_number():
    accounts = [
        account("1100", "Accounts Receivable", "asset", "balance_sheet"),
        account("4200", "Wholesale", "revenue", "operating_revenue"),
        account("4050", "Discounts", "revenue", "contra_revenue"),
        account("4000", "Retail", "revenue", "operating_revenue"),
    ]

    statement = statement_of(accounts=accounts)

    assert [line.account for line in statement.revenue.lines] == ["4000", "4200", "4050"]


def test_account_numbers_of_different_lengths_are_listed_in_number_order():
    accounts = CHART + [account("10000", "Five Digits", "expense", "operating_expense")]

    statement = statement_of(accounts=accounts)

    assert [line.account for line in statement.operating_expenses.lines] == ["6000", "6300", "10000"]


def test_posted_date_span_ignores_drafts_and_voids():
    ledger = parse_ledger(ledger_data(
        entry("JE-1", "2026-01-01", debit("6000", "5.00"), credit("2000", "5.00"), status="draft"),
        entry("JE-2", "2026-02-10", debit("1100", "5.00"), credit("4000", "5.00")),
        entry("JE-3", "2026-03-20", debit("1100", "5.00"), credit("4000", "5.00"), status="void"),
    ))

    assert posted_date_span(ledger) == (day("2026-02-10"), day("2026-02-10"))


def test_posted_date_span_of_a_ledger_with_nothing_posted():
    assert posted_date_span(parse_ledger(ledger_data())) is None


def test_amounts_are_exact_decimals():
    # In binary floating point, 0.10 + 0.20 is 0.30000000000000004.
    statement = statement_of(
        entry("JE-1", "2026-01-05", debit("1100", "0.10"), credit("4000", "0.10")),
        entry("JE-2", "2026-01-06", debit("1100", "0.20"), credit("4000", "0.20")),
    )

    assert statement.revenue.total == D("0.30")
    assert type(statement.revenue.total) is D
    assert type(statement.net_income) is D
