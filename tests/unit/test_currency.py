"""Unit tests: converting an amount and a statement to another currency, and reading a rate."""

from decimal import Decimal as D

import pytest

from builders import amounts, credit, debit, entry, statement_of
from currency import CURRENCIES, convert, convert_statement, parse_rate


def test_the_currencies_offered_and_their_default_rates():
    assert [(choice.code, choice.name, choice.default_rate) for choice in CURRENCIES] == [
        ("EUR", "Euro", D("0.9")),
        ("GBP", "Pound", D("0.7")),
    ]


def test_convert_multiplies_by_the_rate():
    assert convert(D("100.00"), D("0.9")) == D("90.00")
    assert convert(D("100.00"), D("0.7")) == D("70.00")
    assert convert(D("42.18"), D("2")) == D("84.36")


def test_convert_rounds_to_the_cent():
    assert convert(D("0.33"), D("0.7")) == D("0.23")          # 0.231
    assert convert(D("0.37"), D("0.7")) == D("0.26")          # 0.259
    assert convert(D("100.00"), D("0.123456")) == D("12.35")  # 12.3456


def test_convert_rounds_half_a_cent_up():
    # Rounding to the even cent would give 0.12 and 32,085.68, so the first one tells them apart.
    assert convert(D("0.25"), D("0.5")) == D("0.13")            # 0.125
    assert convert(D("35650.75"), D("0.9")) == D("32085.68")    # 32,085.675


def test_a_negative_amount_converts_to_the_same_figure_with_a_minus_sign():
    assert convert(D("-0.25"), D("0.5")) == D("-0.13")       # -0.125, away from zero
    assert convert(D("-800.25"), D("0.9")) == D("-720.23")   # -720.225


def test_convert_always_gives_two_decimal_places():
    assert str(convert(D("5"), D("2"))) == "10.00"
    assert str(convert(D("0.00"), D("0.9"))) == "0.00"


def test_a_small_negative_amount_converts_to_zero_without_a_minus_sign():
    # -0.01 x 0.1 = -0.001. Compared as text, because Decimal counts "-0.00" as equal to "0.00".
    assert str(convert(D("-0.01"), D("0.1"))) == "0.00"


def test_convert_is_exact_for_the_largest_amounts_and_rates():
    # 900,000,000,000,000.01 x 900,000.499995, term by term:
    #   900,000,000,000,000 x 900,000       = 810,000,000,000,000,000,000
    #   900,000,000,000,000 x 0.499995      =         449,995,500,000,000
    #   0.01 x 900,000                      =                       9,000
    #   0.01 x 0.499995                     =                           0.00499995
    # The sum has 29 digits and ends in .00499995, which is below half a cent. Kept to 28
    # digits it would end in .005 and round up.
    assert convert(D("900000000000000.01"), D("900000.499995")) == D("810000449995500009000.00")


def test_each_line_is_converted_and_the_total_is_added_up_from_the_converted_lines():
    recorded = statement_of(
        entry("JE-1", "2026-01-05", debit("6000", "0.05"), credit("1000", "0.05")),
        entry("JE-2", "2026-01-06", debit("6300", "0.05"), credit("1000", "0.05")),
    )

    converted = convert_statement(recorded, "EUR", D("0.5"))

    # 0.05 x 0.5 = 0.025, which rounds to 0.03, twice. The recorded total of 0.10 would
    # convert to 0.05, and then the two lines would not add up to it.
    assert amounts(converted.operating_expenses) == {"6000": D("0.03"), "6300": D("0.03")}
    assert converted.operating_expenses.total == D("0.06")


def test_the_results_are_worked_out_from_the_converted_totals():
    recorded = statement_of(
        entry("JE-1", "2026-01-05", debit("1100", "1.00"), credit("4000", "1.00")),
        entry("JE-2", "2026-01-06", debit("5000", "0.05"), credit("1000", "0.05")),
        entry("JE-3", "2026-01-07", debit("6000", "0.05"), credit("1000", "0.05")),
        entry("JE-4", "2026-01-08", debit("1000", "0.05"), credit("7000", "0.05")),
    )
    assert recorded.net_income == D("0.95")  # 1.00 - 0.05 - 0.05 + 0.05

    converted = convert_statement(recorded, "EUR", D("0.5"))

    # Revenue 1.00 becomes 0.50. Each 0.05 becomes 0.025, which rounds to 0.03.
    assert converted.revenue.total == D("0.50")
    assert converted.cost_of_goods_sold.total == D("0.03")
    assert converted.gross_profit == D("0.47")       # 0.50 - 0.03. Not 0.95 x 0.5 = 0.475, rounded to 0.48
    assert converted.operating_income == D("0.44")   # 0.47 - 0.03
    assert converted.net_income == D("0.47")         # 0.44 + 0.03. Not 0.95 x 0.5 = 0.475, rounded to 0.48


def test_contra_revenue_stays_negative_and_net_revenue_stays_net_of_it():
    recorded = statement_of(
        entry("JE-1", "2026-01-05", debit("1100", "1000.00"), credit("4000", "1000.00")),
        entry("JE-2", "2026-01-06", debit("4900", "800.25"), credit("1100", "800.25")),
    )

    converted = convert_statement(recorded, "EUR", D("0.9"))

    assert amounts(converted.revenue) == {"4000": D("900.00"), "4900": D("-720.23")}  # -800.25 x 0.9 = -720.225
    assert converted.revenue.total == D("179.77")  # 900.00 - 720.23


def test_an_account_with_no_activity_keeps_its_line_at_zero():
    recorded = statement_of(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
    )

    converted = convert_statement(recorded, "GBP", D("0.7"))

    assert amounts(converted.operating_expenses) == {"6000": D("0.00"), "6300": D("0.00")}
    assert {str(line.amount) for line in converted.operating_expenses.lines} == {"0.00"}
    assert converted.net_income == D("70.00")


def test_the_converted_statement_says_which_currency_and_rate_it_is_in():
    recorded = statement_of(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
    )

    converted = convert_statement(recorded, "EUR", D("0.9"))

    assert (recorded.currency, recorded.ledger_currency, recorded.rate) == ("USD", "USD", D("1"))
    assert (converted.currency, converted.ledger_currency, converted.rate) == ("EUR", "USD", D("0.9"))
    assert (converted.company, converted.start, converted.end) == (recorded.company, recorded.start, recorded.end)


def test_the_control_total_and_the_detail_stay_as_recorded():
    recorded = statement_of(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
        entry("JE-2", "2026-01-06", debit("6000", "30.00"), credit("1000", "30.00")),
        entry("JE-3", "2026-01-07", debit("6000", "500.00"), credit("2000", "500.00"), status="draft"),
    )

    converted = convert_statement(recorded, "EUR", D("0.9"))

    assert converted.net_income == D("63.00")  # 90.00 - 27.00
    assert converted.balance_sheet_movement == recorded.balance_sheet_movement
    assert converted.balance_sheet_movement.total == D("70.00")  # 100.00 - 30.00, in the ledger's currency
    assert converted.warnings == recorded.warnings
    for converted_section, recorded_section in zip(converted.sections, recorded.sections, strict=True):
        for converted_line, recorded_line in zip(converted_section.lines, recorded_section.lines, strict=True):
            assert converted_line.debits == recorded_line.debits
            assert converted_line.credits == recorded_line.credits
            assert converted_line.detail == recorded_line.detail


def test_converting_leaves_the_recorded_statement_unchanged():
    recorded = statement_of(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
    )

    convert_statement(recorded, "EUR", D("0.9"))

    assert amounts(recorded.revenue) == {"4000": D("100.00"), "4900": D("0.00")}
    assert recorded.net_income == D("100.00")
    assert recorded.currency == "USD"


@pytest.mark.parametrize("text, rate", [
    ("0.9", D("0.9")),
    ("1", D("1")),
    ("0.90", D("0.90")),
    ("0.000001", D("0.000001")),
    ("1.25", D("1.25")),
    ("999999.999999", D("999999.999999")),
])
def test_parse_rate_reads_a_plain_decimal(text, rate):
    assert parse_rate(text) == rate


@pytest.mark.parametrize("text", [
    "",
    "abc",
    "0",            # a rate of zero would wipe out every amount
    "0.000000",
    "-0.9",
    "+0.9",
    "0.1234567",    # more than six decimal places
    "1000000",      # the limit itself
    "1e2",
    ".9",
    "0.",
    "0,9",
    " 0.9",
    "0.9 EUR",
    "NaN",
    "Infinity",
    "٠.٩",          # digits that are not 0 to 9
])
def test_parse_rate_rejects_anything_else(text):
    assert parse_rate(text) is None
