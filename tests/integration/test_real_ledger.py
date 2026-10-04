"""Integration tests: ledger.json loaded from disk and turned into statements.

Expected values are worked out by hand from ledger.json. The comments show the working.
"""

from datetime import timedelta
from decimal import Decimal as D
from itertools import combinations

import pytest

from builders import LEDGER_PATH, all_amounts, amounts, day, detail_of, every_section
from ledger import load_ledger
from statement import income_statement, posted_date_span


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


def test_q1_2026_balance_sheet_movement(real_ledger):
    statement = income_statement(real_ledger, day("2026-01-01"), day("2026-03-31"))

    # Debits minus credits per balance-sheet account, from the posted Q1 entries.
    assert amounts(statement.balance_sheet_movement) == {
        # in: JE-013 12,450.75 + JE-023 42.18. out: payroll 3 x 18,500.00 + rent 9,000.00
        "1000": D("-52007.07"),
        # billed: 12,450.75 + 12,000.00 + 8,200.00 + 14,850.00. less: return 650.25, payment 12,450.75
        "1100": D("34399.75"),
        "1200": D("-14272.75"),  # the three cost of goods sold entries
        "2000": D("-3600.07"),   # owed: 2,500.10 + 1,199.97, less the 100.00 vendor credit
        "2100": D("-9000.00"),   # 12,000.00 deferred, 3 x 1,000.00 recognized
        "3000": D("0.00"),
    }
    assert statement.balance_sheet_movement.total == D("-44480.14")
    assert statement.balance_sheet_movement.total == statement.net_income


def test_q1_2026_detail_for_product_revenue(real_ledger):
    statement = income_statement(real_ledger, day("2026-01-01"), day("2026-03-31"))

    # Every line on account 4000 in ledger.json, oldest first.
    assert detail_of(statement.revenue, "4000") == [
        ("JE-001", D("0.00"), D("5000.00"), "outside the range"),   # 2025-12-15
        ("JE-002", D("0.00"), D("12450.75"), ""),
        ("JE-009", D("0.00"), D("8200.00"), "void"),
        ("JE-010", D("0.00"), D("8200.00"), ""),
        ("JE-016", D("0.00"), D("15000.00"), ""),
        ("JE-024", D("0.00"), D("9100.00"), "outside the range"),   # 2026-04-01
    ]
    (line,) = [line for line in statement.revenue.lines if line.account == "4000"]
    assert (line.debits, line.credits) == (D("0.00"), D("35650.75"))  # 12,450.75 + 8,200.00 + 15,000.00


def test_q1_2026_detail_for_salaries_shows_the_draft(real_ledger):
    statement = income_statement(real_ledger, day("2026-01-01"), day("2026-03-31"))

    assert detail_of(statement.operating_expenses, "6000") == [
        ("JE-006", D("18500.00"), D("0.00"), ""),
        ("JE-015", D("18500.00"), D("0.00"), ""),
        ("JE-019", D("5000.00"), D("0.00"), "draft"),
        ("JE-022", D("18500.00"), D("0.00"), ""),
    ]


def test_detail_marks_counted_only_when_there_is_no_reason(real_ledger):
    statement = income_statement(real_ledger, day("2026-01-01"), day("2026-03-31"))

    for section in every_section(statement):
        for line in section.lines:
            for item in line.detail:
                assert item.counted == (item.reason == "")


def test_a_void_entry_outside_the_range_is_reported_as_void(real_ledger):
    # JE-009 is void and dated 2026-02-03. For a January statement both reasons apply. Status wins.
    statement = income_statement(real_ledger, day("2026-01-01"), day("2026-01-31"))

    reasons = {entry_id: reason for entry_id, _, _, reason in detail_of(statement.revenue, "4000")}

    assert reasons["JE-009"] == "void"
    assert reasons["JE-010"] == "outside the range"


def test_every_ledger_line_is_listed_exactly_once(real_ledger):
    statement = income_statement(real_ledger, day("2026-01-01"), day("2026-03-31"))

    listed = sum(len(line.detail) for section in every_section(statement) for line in section.lines)

    assert listed == sum(len(entry.lines) for entry in real_ledger.entries) == 51


def test_the_counted_lines_listed_add_up_to_the_amounts_shown(real_ledger):
    """What a reader adds up by hand from the detail must be what the statement shows."""
    days = sorted({entry.date for entry in real_ledger.entries})

    for start, end in combinations(days, 2):
        statement = income_statement(real_ledger, start, end)
        for section in every_section(statement):
            for line in section.lines:
                counted_debits = sum((item.debit for item in line.detail if item.counted), D("0.00"))
                counted_credits = sum((item.credit for item in line.detail if item.counted), D("0.00"))
                assert (counted_debits, counted_credits) == (line.debits, line.credits), (start, end, line.account)
                assert abs(line.amount) == abs(counted_credits - counted_debits), (start, end, line.account)


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


def test_net_income_equals_the_net_movement_in_balance_sheet_accounts(real_ledger):
    """Every entry balances, so the balance sheet side of the posted entries must mirror net income.

    This sums the other half of each entry, the lines the statement never reads. It fails if
    a line lands in the wrong section, gets the wrong sign, or an account is left out.
    """
    entry_days = {entry.date for entry in real_ledger.entries}
    day_before = {d - timedelta(days=1) for d in entry_days}
    day_after = {d + timedelta(days=1) for d in entry_days}
    days = sorted(entry_days | day_before | day_after)

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


def test_posted_date_span_of_the_real_ledger(real_ledger):
    # JE-001 is the first posted entry and JE-024 the last.
    assert posted_date_span(real_ledger) == (day("2025-12-15"), day("2026-04-01"))


def test_q1_2026_reports_the_draft_bonus_accrual_and_nothing_else():
    statement = income_statement(load_ledger(LEDGER_PATH), day("2026-01-01"), day("2026-03-31"))

    (warning,) = statement.warnings
    assert warning["code"] == "draft_not_included"
    assert warning["entry_ids"] == ["JE-019"]
    assert warning["date"] == "2026-03-15"
    assert warning["memo"] == "Q1 bonus accrual (pending approval)"
    assert warning["amount"] == "5000.00"
    assert warning["message"] == (
        "JE-019 (2026-03-15, Q1 bonus accrual (pending approval), 5,000.00) is a draft "
        "and is not included in the totals."
    )
    assert statement.net_income == D("-44480.14")  # the draft's 5,000.00 is not in it


def test_january_2026_has_no_warnings():
    statement = income_statement(load_ledger(LEDGER_PATH), day("2026-01-01"), day("2026-01-31"))

    assert statement.warnings == []


def test_the_voided_double_entry_in_february_is_not_a_possible_duplicate():
    # JE-009 (void) and JE-010 (posted) are identical. The void is the fix, so nothing to report.
    statement = income_statement(load_ledger(LEDGER_PATH), day("2026-02-01"), day("2026-02-28"))

    assert statement.warnings == []
