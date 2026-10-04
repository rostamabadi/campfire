"""Unit tests: reading single values, amounts and dates, from the raw data."""

from datetime import date
from decimal import Decimal

import pytest

from checks import parse_amount, parse_date


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
