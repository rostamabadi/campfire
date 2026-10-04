"""Unit tests: how money is written for JSON and for the page, and how the dates of a request are read."""

from datetime import date
from decimal import Decimal as D

from app import accounting, money, parse_range


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
