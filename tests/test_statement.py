"""The income statement: hand-worked figures on the real ledger, then one test per data trap.

Expected values are worked out by hand from ledger.json. The comments show the working.
"""

from datetime import date, timedelta
from decimal import Decimal as D
from itertools import combinations
from pathlib import Path

import pytest

from builders import CHART, account, allow_a_subtype_that_no_section_uses, credit, debit, entry, ledger_data
from ledger import load_ledger, parse_ledger
from statement import ControlTotalError, income_statement

LEDGER_PATH = Path(__file__).parent.parent / "ledger.json"


@pytest.fixture(scope="module")
def real_ledger():
    return load_ledger(LEDGER_PATH)


def day(text):
    return date.fromisoformat(text)


def amounts(section):
    return {line.account: line.amount for line in section.lines}


def all_amounts(statement):
    """Every line on the statement, by account number."""
    return {
        **amounts(statement.revenue),
        **amounts(statement.cost_of_goods_sold),
        **amounts(statement.operating_expenses),
        **amounts(statement.other_income),
    }


def statement_of(*entries, start="2026-01-01", end="2026-12-31", accounts=CHART):
    ledger = parse_ledger(ledger_data(*entries, accounts=accounts))
    return income_statement(ledger, day(start), day(end))


# --- the real ledger, against figures worked out by hand ---

def test_q1_2026_every_line_and_subtotal(real_ledger):
    statement = income_statement(real_ledger, day("2026-01-01"), day("2026-03-31"))

    assert amounts(statement.revenue) == {
        "4000": D("35650.75"),  # JE-002 12,450.75 + JE-010 8,200.00 + JE-016 15,000.00 (JE-009 is void)
        "4100": D("3000.00"),   # JE-005 + JE-014 + JE-021, 1,000.00 each (JE-004 only defers)
        "4900": D("-800.25"),   # JE-012 650.25 + JE-016 150.00, both debits
    }
    assert statement.revenue.total == D("37850.50")

    assert amounts(statement.cost_of_goods_sold) == {
        "5000": D("14272.75"),  # JE-003 4,980.30 + JE-011 3,280.00 + JE-017 6,012.45
    }
    assert statement.cost_of_goods_sold.total == D("14272.75")
    assert statement.gross_profit == D("23577.75")  # 37,850.50 - 14,272.75

    assert amounts(statement.operating_expenses) == {
        "6000": D("55500.00"),  # JE-006 + JE-015 + JE-022, 18,500.00 each (JE-019 is a draft)
        "6100": D("9000.00"),   # JE-007
        "6200": D("1099.97"),   # JE-018 1,199.97 less the JE-020 credit of 100.00
        "6300": D("2500.10"),   # JE-008, posted to an inactive account
    }
    assert statement.operating_expenses.total == D("68100.07")
    assert statement.operating_income == D("-44522.32")  # 23,577.75 - 68,100.07

    assert amounts(statement.other_income) == {"7000": D("42.18")}  # JE-023
    assert statement.other_income.total == D("42.18")
    assert statement.net_income == D("-44480.14")  # -44,522.32 + 42.18


@pytest.mark.parametrize(
    "start, end, net_revenue, cogs, operating_expenses, other_income, net_income",
    [
        # January: sales 12,450.75 + subscription 1,000.00. Expenses: payroll 18,500.00,
        # all three months of rent 9,000.00 (JE-007, as recorded), marketing 2,500.10.
        ("2026-01-01", "2026-01-31", "13450.75", "4980.30", "30000.10", "0.00", "-21529.65"),
        # February: sales 8,200.00 + subscription 1,000.00 - return 650.25. Payroll only.
        ("2026-02-01", "2026-02-28", "8549.75", "3280.00", "18500.00", "0.00", "-13230.25"),
        # March: sales 15,000.00 + subscription 1,000.00 - discount 150.00.
        # Payroll 18,500.00 + software 1,099.97. Interest 42.18.
        ("2026-03-01", "2026-03-31", "15850.00", "6012.45", "19599.97", "42.18", "-9720.24"),
    ],
)
def test_each_month_of_q1(real_ledger, start, end, net_revenue, cogs, operating_expenses, other_income, net_income):
    statement = income_statement(real_ledger, day(start), day(end))

    assert statement.revenue.total == D(net_revenue)
    assert statement.cost_of_goods_sold.total == D(cogs)
    assert statement.operating_expenses.total == D(operating_expenses)
    assert statement.other_income.total == D(other_income)
    assert statement.net_income == D(net_income)


@pytest.mark.parametrize(
    "start, end, net_income",
    [
        ("2026-03-31", "2026-03-31", "-17457.82"),  # one day: 1,000.00 - 18,500.00 + 42.18
        ("2026-01-01", "2026-01-01", "-9000.00"),   # one day: rent, dated on the first day of Q1
        ("2026-01-02", "2026-03-30", "-18022.32"),  # Q1 without its first and last day
        ("2025-12-01", "2025-12-31", "5000.00"),    # JE-001, before Q1
        ("2026-04-01", "2026-04-30", "9100.00"),    # JE-024, after Q1
        ("2025-12-15", "2026-04-01", "-30380.14"),  # everything: 5,000.00 - 44,480.14 + 9,100.00
        ("2025-01-01", "2025-06-30", "0.00"),       # before any entry
    ],
)
def test_net_income_for_other_ranges(real_ledger, start, end, net_income):
    assert income_statement(real_ledger, day(start), day(end)).net_income == D(net_income)


def test_range_with_no_activity_lists_every_account_at_zero(real_ledger):
    statement = income_statement(real_ledger, day("2025-01-01"), day("2025-06-30"))

    assert [line.account for line in statement.revenue.lines] == ["4000", "4100", "4900"]
    assert [line.account for line in statement.cost_of_goods_sold.lines] == ["5000"]
    assert [line.account for line in statement.operating_expenses.lines] == ["6000", "6100", "6200", "6300"]
    assert [line.account for line in statement.other_income.lines] == ["7000"]
    # Compare as text so that a negative zero, "-0.00", would fail.
    assert {str(amount) for amount in all_amounts(statement).values()} == {"0.00"}
    assert str(statement.net_income) == "0.00"


# --- invariants on the real ledger, over many ranges ---

def test_net_income_equals_the_net_movement_in_balance_sheet_accounts(real_ledger):
    """Every entry balances, so the balance sheet side of the posted entries must mirror net income.

    This sums the other half of each entry, the lines the statement never reads. It fails if
    a line lands in the wrong section, gets the wrong sign, or an account is left out.
    """
    entry_days = {entry.date for entry in real_ledger.entries}
    days = sorted(entry_days | {d - timedelta(days=1) for d in entry_days} | {d + timedelta(days=1) for d in entry_days})

    for start in days:
        for end in days:
            if start > end:
                continue
            net_debits = D("0.00")
            for entry_ in real_ledger.entries:
                if entry_.status == "posted" and start <= entry_.date <= end:
                    for line in entry_.lines:
                        if real_ledger.accounts[line.account].subtype == "balance_sheet":
                            net_debits += line.debit - line.credit

            assert income_statement(real_ledger, start, end).net_income == net_debits, (start, end)


def test_two_adjacent_ranges_add_up_to_the_whole_range(real_ledger):
    days = sorted({entry.date for entry in real_ledger.entries})

    for start, split, end in combinations(days, 3):  # start < split < end
        whole = income_statement(real_ledger, start, end)
        first = income_statement(real_ledger, start, split)
        second = income_statement(real_ledger, split + timedelta(days=1), end)

        assert first.net_income + second.net_income == whole.net_income, (start, split, end)
        for number, amount in all_amounts(whole).items():
            assert all_amounts(first)[number] + all_amounts(second)[number] == amount, (start, split, end, number)


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


# --- one small ledger per trap ---

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


def test_amounts_are_exact_decimals():
    # In binary floating point, 0.10 + 0.20 is 0.30000000000000004.
    statement = statement_of(
        entry("JE-1", "2026-01-05", debit("1100", "0.10"), credit("4000", "0.10")),
        entry("JE-2", "2026-01-06", debit("1100", "0.20"), credit("4000", "0.20")),
    )

    assert statement.revenue.total == D("0.30")
    assert type(statement.revenue.total) is D
    assert type(statement.net_income) is D
