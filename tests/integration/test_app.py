"""Integration tests: the HTTP layer through Flask's test client. The JSON, the page, and every error path."""

import json

import pytest

from app import create_app
from builders import allow_a_subtype_that_no_section_uses, credit, debit, entry, ledger_data

Q1 = "start=2026-01-01&end=2026-03-31"


@pytest.fixture
def client():
    return create_app().test_client()


@pytest.fixture
def client_with_bad_ledger(tmp_path):
    """An app whose ledger has two problems: an entry that does not balance and a reused id."""
    data = ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "90.00")),
        entry("JE-2", "2026-01-06", debit("1100", "50.00"), credit("4000", "50.00")),
        entry("JE-2", "2026-01-07", debit("1100", "60.00"), credit("4000", "60.00")),
    )
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(data))
    return create_app(path).test_client()


def error_summary(response):
    return [(error["code"], error["field"]) for error in response.get_json()["errors"]]


def test_q1_2026_json(client):
    response = client.get(f"/income-statement?{Q1}")

    assert response.status_code == 200
    assert response.get_json() == {
        "company": "Northwind Coffee Roasters",
        "currency": "USD",
        "start": "2026-01-01",
        "end": "2026-03-31",
        "revenue": {
            "lines": [
                {"account": "4000", "name": "Product Revenue", "amount": "35650.75"},
                {"account": "4100", "name": "Subscription Revenue", "amount": "3000.00"},
                {"account": "4900", "name": "Sales Returns & Discounts", "amount": "-800.25"},
            ],
            "total": "37850.50",
        },
        "cost_of_goods_sold": {
            "lines": [{"account": "5000", "name": "Cost of Goods Sold", "amount": "14272.75"}],
            "total": "14272.75",
        },
        "gross_profit": "23577.75",
        "operating_expenses": {
            "lines": [
                {"account": "6000", "name": "Salaries", "amount": "55500.00"},
                {"account": "6100", "name": "Rent", "amount": "9000.00"},
                {"account": "6200", "name": "Software", "amount": "1099.97"},
                {"account": "6300", "name": "Marketing (legacy)", "amount": "2500.10"},
            ],
            "total": "68100.07",
        },
        "operating_income": "-44522.32",
        "other_income": {
            "lines": [{"account": "7000", "name": "Interest Income", "amount": "42.18"}],
            "total": "42.18",
        },
        "net_income": "-44480.14",
        "balance_sheet_movement": {
            "lines": [
                {"account": "1000", "name": "Cash", "amount": "-52007.07"},
                {"account": "1100", "name": "Accounts Receivable", "amount": "34399.75"},
                {"account": "1200", "name": "Inventory", "amount": "-14272.75"},
                {"account": "2000", "name": "Accounts Payable", "amount": "-3600.07"},
                {"account": "2100", "name": "Deferred Revenue", "amount": "-9000.00"},
                {"account": "3000", "name": "Retained Earnings", "amount": "0.00"},
            ],
            "total": "-44480.14",
        },
        "warnings": [
            {
                "code": "draft_not_included",
                "entry_ids": ["JE-019"],
                "date": "2026-03-15",
                "memo": "Q1 bonus accrual (pending approval)",
                "amount": "5000.00",
                "message": "JE-019 (2026-03-15, Q1 bonus accrual (pending approval), 5,000.00) is a draft "
                           "and is not included in the totals.",
            }
        ],
    }


def test_json_keeps_the_order_of_the_statement(client):
    response = client.get(f"/income-statement?{Q1}")

    assert list(json.loads(response.text)) == [
        "company", "currency", "start", "end",
        "revenue", "cost_of_goods_sold", "gross_profit",
        "operating_expenses", "operating_income",
        "other_income", "net_income", "balance_sheet_movement", "warnings",
    ]


def test_json_carries_no_numbers_only_decimal_strings(client):
    def reject(token):
        raise AssertionError(f"number in the JSON: {token}")

    response = client.get(f"/income-statement?{Q1}")

    json.loads(response.text, parse_float=reject, parse_int=reject)


def test_a_range_with_no_activity_is_a_statement_of_zeros(client):
    body = client.get("/income-statement?start=2025-01-01&end=2025-06-30").get_json()

    assert body["net_income"] == "0.00"
    assert body["revenue"]["total"] == "0.00"
    assert {line["amount"] for line in body["operating_expenses"]["lines"]} == {"0.00"}
    assert body["warnings"] == []


def test_start_and_end_on_the_same_day(client):
    response = client.get("/income-statement?start=2026-03-31&end=2026-03-31")

    assert response.status_code == 200
    assert response.get_json()["net_income"] == "-17457.82"  # 1,000.00 - 18,500.00 + 42.18


def test_missing_dates_are_both_reported(client):
    response = client.get("/income-statement")

    assert response.status_code == 400
    assert error_summary(response) == [("missing_parameter", "start"), ("missing_parameter", "end")]


def test_blank_date_counts_as_missing(client):
    response = client.get("/income-statement?start=&end=2026-03-31")

    assert response.status_code == 400
    assert error_summary(response) == [("missing_parameter", "start")]


@pytest.mark.parametrize("bad_date", ["2026-02-30", "01/31/2026", "2026-1-5", "yesterday"])
def test_invalid_date(client, bad_date):
    response = client.get("/income-statement", query_string={"start": "2026-01-01", "end": bad_date})

    assert response.status_code == 400
    assert error_summary(response) == [("invalid_date", "end")]
    assert bad_date in response.get_json()["errors"][0]["message"]


def test_start_after_end(client):
    response = client.get("/income-statement?start=2026-04-01&end=2026-03-31")

    assert response.status_code == 400
    assert error_summary(response) == [("invalid_range", "start")]
    assert response.get_json()["errors"][0]["message"] == (
        "The start date 2026-04-01 is after the end date 2026-03-31."
    )


def test_a_bad_ledger_returns_every_problem_and_no_numbers(client_with_bad_ledger):
    response = client_with_bad_ledger.get(f"/income-statement?{Q1}")

    assert response.status_code == 500
    body = response.get_json()
    assert list(body) == ["errors"]
    assert [(error["code"], error["entry_id"]) for error in body["errors"]] == [
        ("unbalanced_entry", "JE-1"),
        ("duplicate_id", "JE-2"),
    ]
    assert body["errors"][0]["message"] == "JE-1 does not balance: debits 100.00, credits 90.00."


def test_an_unreadable_ledger_is_reported(tmp_path):
    client = create_app(tmp_path / "nothing-here.json").test_client()

    response = client.get(f"/income-statement?{Q1}")

    assert response.status_code == 500
    assert [error["code"] for error in response.get_json()["errors"]] == ["unreadable_ledger"]


def test_a_control_total_mismatch_is_an_error_not_a_statement(tmp_path, monkeypatch):
    accounts = allow_a_subtype_that_no_section_uses(monkeypatch)
    data = ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
        entry("JE-2", "2026-01-06", debit("7500", "30.00"), credit("1000", "30.00")),
        accounts=accounts,
    )
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(data))
    client = create_app(path).test_client()

    api_response = client.get(f"/income-statement?{Q1}")
    page_response = client.get(f"/?{Q1}")

    assert api_response.status_code == 500
    assert [error["code"] for error in api_response.get_json()["errors"]] == ["control_total_mismatch"]
    assert page_response.status_code == 500
    assert "net income is 100.00 but the balance-sheet accounts moved by 70.00" in page_response.text
    assert "Net income" not in page_response.text


def test_first_visit_goes_to_the_whole_ledger(client):
    response = client.get("/")

    # From the first posted entry, JE-001, to the last, JE-024.
    assert response.status_code == 302
    assert response.headers["Location"] == "/?start=2025-12-15&end=2026-04-01"

    page = client.get("/", follow_redirects=True)

    assert page.status_code == 200
    assert 'value="2025-12-15"' in page.text and 'value="2026-04-01"' in page.text
    assert "(30,380.14)" in page.text  # 5,000.00 - 44,480.14 + 9,100.00
    assert "could not be shown" not in page.text


def test_first_visit_with_nothing_posted_shows_only_the_form(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(ledger_data()))

    response = create_app(path).test_client().get("/")

    assert response.status_code == 200
    assert 'name="start"' in response.text and 'name="end"' in response.text
    assert "could not be shown" not in response.text
    assert "Net income" not in response.text


def test_an_edit_to_the_ledger_file_shows_up_without_a_restart(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
    )))
    client = create_app(path).test_client()
    assert client.get(f"/income-statement?{Q1}").get_json()["net_income"] == "100.00"

    path.write_text(json.dumps(ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
        entry("JE-2", "2026-01-06", debit("1100", "25.50"), credit("4000", "25.50")),
    )))

    assert client.get(f"/income-statement?{Q1}").get_json()["net_income"] == "125.50"


def test_a_problem_in_a_draft_is_shown_as_a_note_and_the_statement_still_appears(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(ledger_data(
        entry("JE-1", "2026-01-05", debit("1100", "100.00"), credit("4000", "100.00")),
        entry("JE-2", "2026-01-06", debit("6000", "500.00"), credit("2000", "400.00"), status="draft"),
    )))
    client = create_app(path).test_client()

    api_response = client.get(f"/income-statement?{Q1}")
    page_response = client.get(f"/?{Q1}")

    assert api_response.status_code == 200
    assert api_response.get_json()["net_income"] == "100.00"
    assert [warning["code"] for warning in api_response.get_json()["warnings"]] == ["unbalanced_entry"]
    assert page_response.status_code == 200
    assert "JE-2 does not balance: debits 500.00, credits 400.00. This entry is a draft" in page_response.text


def test_an_unknown_url_returns_the_json_error_shape(client):
    response = client.get("/nope")

    assert response.status_code == 404
    assert [error["code"] for error in response.get_json()["errors"]] == ["not_found"]


def test_a_wrong_method_returns_the_json_error_shape(client):
    response = client.post("/income-statement")

    assert response.status_code == 405
    assert [error["code"] for error in response.get_json()["errors"]] == ["method_not_allowed"]


def test_an_unexpected_failure_returns_the_json_error_shape(client, monkeypatch):
    def fail(*args):
        raise RuntimeError("something broke")

    monkeypatch.setattr("app.income_statement", fail)

    response = client.get(f"/income-statement?{Q1}")

    assert response.status_code == 500
    body = response.get_json()
    assert [error["code"] for error in body["errors"]] == ["internal_server_error"]
    assert "something broke" not in response.text  # no internals in the response


def test_page_shows_q1_2026_the_way_an_accountant_reads_it(client):
    response = client.get(f"/?{Q1}")

    assert response.status_code == 200
    text = response.text
    assert "Northwind Coffee Roasters" in text
    assert "4900 Sales Returns &amp; Discounts" in text
    assert "(800.25)" in text       # contra revenue
    assert "37,850.50" in text      # net revenue
    assert "23,577.75" in text      # gross profit
    assert "(44,522.32)" in text    # operating income
    assert "(44,480.14)" in text    # net income
    assert "JE-019" in text         # the draft warning
    assert 'value="2026-01-01"' in text and 'value="2026-03-31"' in text  # the form keeps the dates


def test_page_shows_the_balance_sheet_movement_that_backs_the_control_total(client):
    text = client.get(f"/?{Q1}").text

    assert "<summary>Check: movement in balance-sheet accounts</summary>" in text
    assert "<details>" in text and "<details open" not in text  # collapsed until clicked
    assert "1000 Cash" in text
    assert "(52,007.07)" in text   # cash went down
    assert "34,399.75" in text     # receivables went up
    # Net income, the movement total that equals it, and the same total again in the detail.
    assert text.count("(44,480.14)") == 3


def test_page_lists_every_journal_line_under_its_account(client):
    text = client.get(f"/?{Q1}").text

    assert "<summary>Detail: every journal line, by account</summary>" in text
    assert "<summary>4000 Product Revenue: 35,650.75</summary>" in text
    assert "<summary>6100 Rent: 9,000.00</summary>" in text
    assert "<details open" not in text  # the detail and every account in it start collapsed

    # Lines that do not count are marked for strike-through and say why. For Q1 those are the
    # two lines each of JE-001 and JE-024 (outside the range), JE-009 and JE-025 (void) and
    # JE-019 (draft).
    assert text.count('<tr class="not-counted">') == 10
    for reason in ["no, void", "no, draft", "no, outside the range"]:
        assert reason in text
    assert "February product sales (entered twice)" in text  # the void JE-009 is still listed


def test_page_sections_appear_in_statement_order(client):
    text = client.get(f"/?{Q1}").text
    labels = [
        "Revenue", "Net revenue", "Cost of goods sold", "Gross profit",
        "Operating expenses", "Operating income", "Other income", "Net income",
    ]

    positions = [text.index(f">{label}<") for label in labels]

    assert positions == sorted(positions)


def test_page_shows_request_errors_and_no_statement(client):
    response = client.get("/?start=2026-04-01&end=2026-03-31")

    assert response.status_code == 400
    assert "The start date 2026-04-01 is after the end date 2026-03-31." in response.text
    assert "Net income" not in response.text


def test_page_reports_a_blank_date(client):
    response = client.get("/?start=&end=")

    assert response.status_code == 400
    assert "The start date is required" in response.text
    assert "The end date is required" in response.text


def test_page_escapes_what_the_user_typed(client):
    response = client.get("/", query_string={"start": "<script>alert(1)</script>", "end": "2026-03-31"})

    assert response.status_code == 400
    assert "<script>alert(1)</script>" not in response.text


def test_page_shows_ledger_errors_even_on_the_first_visit(client_with_bad_ledger):
    response = client_with_bad_ledger.get("/")

    assert response.status_code == 500
    assert "JE-1 does not balance: debits 100.00, credits 90.00." in response.text
    assert "Entry id JE-2 is used by more than one journal entry." in response.text
    assert "Net income" not in response.text
