"""The web app: GET /income-statement returns JSON, GET / renders the same statement as a page."""

from decimal import Decimal
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

from ledger import LedgerError, load_ledger, parse_date
from statement import ControlTotalError, IncomeStatement, Section, income_statement, posted_date_span

LEDGER_PATH = Path(__file__).with_name("ledger.json")


def money(amount: Decimal) -> str:
    """Amount for JSON: a plain decimal string with two places, such as "-44480.14"."""
    return f"{amount:.2f}"


def accounting(amount: Decimal) -> str:
    """Amount for the page: thousands separators, and parentheses for negatives, such as (44,480.14)."""
    if amount < 0:
        return f"({-amount:,.2f})"
    return f"{amount:,.2f}"


def parse_range(args) -> tuple:
    """Read start and end from the query string. Returns (start, end, errors)."""
    errors = []
    dates = {}
    for field in ("start", "end"):
        text = args.get(field, "").strip()
        if not text:
            errors.append({
                "code": "missing_parameter",
                "field": field,
                "message": f"The {field} date is required, as YYYY-MM-DD.",
            })
            continue
        dates[field] = parse_date(text)
        if dates[field] is None:
            errors.append({
                "code": "invalid_date",
                "field": field,
                "message": f"The {field} date '{text}' is not a valid date. Use YYYY-MM-DD, such as 2026-01-31.",
            })

    if not errors and dates["start"] > dates["end"]:
        errors.append({
            "code": "invalid_range",
            "field": "start",
            "message": f"The start date {dates['start']} is after the end date {dates['end']}.",
        })

    return dates.get("start"), dates.get("end"), errors


def section_json(section: Section) -> dict:
    return {
        "lines": [
            {"account": line.account, "name": line.name, "amount": money(line.amount)}
            for line in section.lines
        ],
        "total": money(section.total),
    }


def statement_json(statement: IncomeStatement) -> dict:
    return {
        "company": statement.company,
        "currency": statement.currency,
        "start": statement.start.isoformat(),
        "end": statement.end.isoformat(),
        "revenue": section_json(statement.revenue),
        "cost_of_goods_sold": section_json(statement.cost_of_goods_sold),
        "gross_profit": money(statement.gross_profit),
        "operating_expenses": section_json(statement.operating_expenses),
        "operating_income": money(statement.operating_income),
        "other_income": section_json(statement.other_income),
        "net_income": money(statement.net_income),
        "balance_sheet_movement": section_json(statement.balance_sheet_movement),
        "warnings": statement.warnings,
    }


def create_app(ledger_path=LEDGER_PATH) -> Flask:
    app = Flask(__name__)
    app.json.sort_keys = False  # keep the statement's order in the JSON
    app.jinja_env.filters["accounting"] = accounting

    def read_ledger() -> tuple:
        """Returns (ledger, errors). The file is read on every request, so an edit to it shows
        up without a restart. It is small. A real system would query a database here.

        If the data has blocking problems there is no ledger, and the request reports the
        problems instead of showing numbers that might be wrong.
        """
        try:
            return load_ledger(ledger_path), []
        except LedgerError as problem:
            return None, problem.errors

    def statement_for_request(ledger, ledger_errors) -> tuple:
        """Returns (statement, errors, http_status) for the start and end in the query string."""
        if ledger_errors:
            return None, ledger_errors, 500
        start, end, errors = parse_range(request.args)
        if errors:
            return None, errors, 400
        try:
            return income_statement(ledger, start, end), [], 200
        except ControlTotalError as problem:
            return None, [problem.error], 500

    @app.get("/income-statement")
    def income_statement_api():
        ledger, ledger_errors = read_ledger()
        statement, errors, status = statement_for_request(ledger, ledger_errors)
        if errors:
            return {"errors": errors}, status
        return statement_json(statement)

    @app.get("/")
    def income_statement_page():
        ledger, ledger_errors = read_ledger()

        # With no query string this is a first visit. Go to the whole ledger, from its first
        # posted entry to its last. If nothing is posted yet, show only the form.
        if not request.args and not ledger_errors:
            span = posted_date_span(ledger)
            if span is None:
                return render_template("statement.html", statement=None, errors=[], start="", end="")
            first, last = span
            return redirect(url_for("income_statement_page", start=first.isoformat(), end=last.isoformat()))

        statement, errors, status = statement_for_request(ledger, ledger_errors)
        page = render_template(
            "statement.html",
            statement=statement,
            errors=errors,
            start=request.args.get("start", ""),
            end=request.args.get("end", ""),
        )
        return page, status

    @app.errorhandler(HTTPException)
    def http_error(problem):
        """Unknown URLs, wrong methods and unexpected failures, in the same shape as every other error."""
        code = problem.name.lower().replace(" ", "_")  # "Not Found" becomes "not_found"
        return {"errors": [{"code": code, "message": problem.description}]}, problem.code

    return app
