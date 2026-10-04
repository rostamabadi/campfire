"""Unit tests: warnings for drafts, possible duplicates, and problems in entries that do not count."""

from decimal import Decimal as D

from builders import credit, debit, entry, statement_of


def test_a_draft_outside_the_range_is_not_reported():
    statement = statement_of(
        entry("JE-1", "2026-03-15", debit("6000", "500.00"), credit("2000", "500.00"), status="draft"),
        start="2026-01-01",
        end="2026-02-28",
    )

    assert statement.warnings == []


def test_each_draft_in_the_range_gets_its_own_warning():
    statement = statement_of(
        entry("JE-1", "2026-03-15", debit("6000", "500.00"), credit("2000", "500.00"), status="draft"),
        entry("JE-2", "2026-03-16", debit("6000", "70.00"), credit("2000", "70.00"), status="draft"),
    )

    assert [warning["entry_ids"] for warning in statement.warnings] == [["JE-1"], ["JE-2"]]
    assert statement.net_income == D("0.00")


def test_void_entries_are_not_reported():
    statement = statement_of(
        entry("JE-1", "2026-03-15", debit("6000", "500.00"), credit("2000", "500.00"), status="void"),
    )

    assert statement.warnings == []


def test_a_problem_in_a_draft_is_reported_on_every_statement_and_changes_no_total():
    # The draft does not balance. It is dated in March, the statement is for January.
    statement = statement_of(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
        entry("JE-2", "2026-03-15", debit("6000", "500.00"), credit("2000", "400.00"), status="draft"),
        start="2026-01-01",
        end="2026-01-31",
    )

    assert [(warning["code"], warning["entry_id"]) for warning in statement.warnings] == [
        ("unbalanced_entry", "JE-2"),
    ]
    assert statement.net_income == D("100.00")


def test_two_posted_entries_with_the_same_date_and_lines_are_reported_and_both_counted():
    statement = statement_of(
        entry("JE-1", "2026-02-03", debit("1100", "8200.00"), credit("4000", "8200.00")),
        entry("JE-2", "2026-02-03", debit("1100", "8200.00"), credit("4000", "8200.00")),
    )

    (warning,) = statement.warnings
    assert warning["code"] == "possible_duplicate"
    assert warning["entry_ids"] == ["JE-1", "JE-2"]
    assert warning["date"] == "2026-02-03"
    assert "JE-1 and JE-2" in warning["message"]
    assert statement.revenue.total == D("16400.00")  # as recorded: nothing is dropped


def test_line_order_and_amount_formatting_do_not_hide_a_duplicate():
    statement = statement_of(
        entry("JE-1", "2026-02-03", debit("1100", "8200.00"), credit("4000", "8200.00")),
        entry("JE-2", "2026-02-03", credit("4000", "8200.0"), debit("1100", "8200")),
    )

    assert [warning["code"] for warning in statement.warnings] == ["possible_duplicate"]


def test_the_same_lines_on_different_dates_are_not_duplicates():
    # Monthly payroll looks the same every month.
    statement = statement_of(
        entry("JE-1", "2026-01-31", debit("6000", "18500.00"), credit("1000", "18500.00")),
        entry("JE-2", "2026-02-28", debit("6000", "18500.00"), credit("1000", "18500.00")),
    )

    assert statement.warnings == []


def test_different_amounts_on_the_same_date_are_not_duplicates():
    statement = statement_of(
        entry("JE-1", "2026-02-03", debit("1100", "8200.00"), credit("4000", "8200.00")),
        entry("JE-2", "2026-02-03", debit("1100", "8200.01"), credit("4000", "8200.01")),
    )

    assert statement.warnings == []


def test_a_posted_entry_with_a_void_twin_is_not_a_possible_duplicate():
    statement = statement_of(
        entry("JE-1", "2026-02-03", debit("1100", "8200.00"), credit("4000", "8200.00")),
        entry("JE-2", "2026-02-03", debit("1100", "8200.00"), credit("4000", "8200.00"), status="void"),
    )

    assert statement.warnings == []
    assert statement.revenue.total == D("8200.00")
