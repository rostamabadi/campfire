"""Unit tests: how money is written for JSON and for the page, and how the dates and the currency of a
request are read."""

from datetime import date
from decimal import Decimal as D

import pytest

from app import accounting, money, parse_currency, parse_range


def test_money_for_json():
    assert money(D("-44480.14")) == "-44480.14"
    assert money(D("5000")) == "5000.00"
    assert money(D("0.00")) == "0.00"


def test_money_for_the_page():
    assert accounting(D("35650.75")) == "35,650.75"
    assert accounting(D("-44480.14")) == "(44,480.14)"
    assert accounting(D("0.00")) == "0.00"


def test_parse_range_reads_both_dates():
    assert parse_range({"start": "2026-01-01", "end": "2026-03-31"}) == (date(2026, 1, 1), date(2026, 3, 31), [])


def test_parse_range_accepts_the_same_day_twice():
    start, end, errors = parse_range({"start": "2026-03-31", "end": "2026-03-31"})

    assert (start, end, errors) == (date(2026, 3, 31), date(2026, 3, 31), [])


def test_parse_range_reports_every_problem_at_once():
    start, end, errors = parse_range({"end": "2026-02-30"})

    assert [(error["code"], error["field"]) for error in errors] == [
        ("missing_parameter", "start"),
        ("invalid_date", "end"),
    ]


def test_parse_range_rejects_a_start_after_the_end():
    start, end, errors = parse_range({"start": "2026-04-01", "end": "2026-03-31"})

    assert [(error["code"], error["field"]) for error in errors] == [("invalid_range", "start")]


def summary(errors):
    return [(error["code"], error["field"]) for error in errors]


def test_parse_currency_converts_nothing_unless_asked():
    assert parse_currency({}, "USD") == ("USD", D("1"), [])
    assert parse_currency({"currency": "", "rate": ""}, "USD") == ("USD", D("1"), [])
    assert parse_currency({"currency": "USD", "rate": ""}, "USD") == ("USD", D("1"), [])


def test_parse_currency_uses_the_default_rate_when_none_is_typed():
    assert parse_currency({"currency": "EUR"}, "USD") == ("EUR", D("0.9"), [])
    assert parse_currency({"currency": "GBP", "rate": ""}, "USD") == ("GBP", D("0.7"), [])


def test_parse_currency_uses_the_rate_typed():
    assert parse_currency({"currency": "EUR", "rate": "0.9137"}, "USD") == ("EUR", D("0.9137"), [])
    assert parse_currency({"currency": "GBP", "rate": " 0.75 "}, "USD") == ("GBP", D("0.75"), [])


@pytest.mark.parametrize("code", ["JPY", "eur", "Euro", "$"])
def test_parse_currency_rejects_a_currency_that_is_not_offered(code):
    currency, rate, errors = parse_currency({"currency": code}, "USD")

    assert (currency, rate) == ("USD", D("1"))
    assert summary(errors) == [("invalid_currency", "currency")]
    assert errors[0]["message"] == f"The currency '{code}' is not available. Use one of: USD, EUR, GBP."


@pytest.mark.parametrize("rate_text", ["abc", "0", "-0.9", "0.1234567", "1000000", "1e2"])
def test_parse_currency_rejects_a_rate_that_is_not_valid(rate_text):
    currency, rate, errors = parse_currency({"currency": "EUR", "rate": rate_text}, "USD")

    assert (currency, rate) == ("USD", D("1"))
    assert summary(errors) == [("invalid_rate", "rate")]
    assert errors[0]["message"] == (
        f"The rate '{rate_text}' is not a valid rate. Use a number above 0 and below 1,000,000 "
        "with at most 6 decimal places, such as 0.9."
    )


@pytest.mark.parametrize("args", [
    {"currency": "USD", "rate": "0.9"},
    {"currency": "USD", "rate": "1"},
    {"rate": "0.9"},
])
def test_parse_currency_rejects_a_rate_for_the_ledgers_own_currency(args):
    currency, rate, errors = parse_currency(args, "USD")

    assert (currency, rate) == ("USD", D("1"))
    assert summary(errors) == [("invalid_rate", "rate")]
    assert errors[0]["message"] == (
        "USD is the ledger's own currency, so no rate applies. Leave the rate blank, or choose another currency."
    )


def test_parse_currency_reports_a_bad_currency_and_a_bad_rate_together():
    currency, rate, errors = parse_currency({"currency": "JPY", "rate": "abc"}, "USD")

    assert (currency, rate) == ("USD", D("1"))
    assert summary(errors) == [("invalid_currency", "currency"), ("invalid_rate", "rate")]


def test_parse_currency_does_not_convert_a_ledger_that_is_not_in_dollars():
    # The default rates are per US dollar, so they say nothing about a ledger in Canadian dollars.
    assert parse_currency({}, "CAD") == ("CAD", D("1"), [])
    assert parse_currency({"currency": "CAD"}, "CAD") == ("CAD", D("1"), [])

    for code in ["EUR", "USD"]:
        currency, rate, errors = parse_currency({"currency": code, "rate": "0.9"}, "CAD")

        assert (currency, rate) == ("CAD", D("1"))
        assert summary(errors) == [("invalid_currency", "currency")]
        assert errors[0]["message"] == "The ledger is in CAD. The rates are per USD, so it cannot be converted."
