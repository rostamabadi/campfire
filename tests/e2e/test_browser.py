"""End-to-end tests: a real browser against the running app, with the real ledger.json.

Run with: uv run pytest tests/e2e
The browser is installed once with: uv run playwright install chromium
"""

import re

from playwright.sync_api import Page, expect

Q1 = "/?start=2026-01-01&end=2026-03-31"


def net_income(page: Page):
    return page.locator("tr.net td.amount")


def test_first_visit_opens_on_the_whole_ledger(page: Page):
    page.goto("/")

    expect(page).to_have_url(re.compile(r"/\?start=2025-12-15&end=2026-04-01$"))
    expect(net_income(page)).to_have_text("(30,380.14)")  # 5,000.00 - 44,480.14 + 9,100.00


def test_choosing_q1_in_the_form_shows_the_q1_statement(page: Page):
    page.goto("/")
    page.get_by_label("Start date").fill("2026-01-01")
    page.get_by_label("End date").fill("2026-03-31")
    page.get_by_role("button", name="Show statement").click()

    expect(net_income(page)).to_have_text("(44,480.14)")
    expect(page.locator("tr", has_text="4900 Sales Returns & Discounts")).to_contain_text("(800.25)")
    expect(page.locator(".warnings")).to_contain_text("JE-019")  # the draft is pointed out
    expect(page.get_by_label("Start date")).to_have_value("2026-01-01")  # the form keeps the dates


def test_a_start_after_the_end_shows_the_error_and_no_statement(page: Page):
    page.goto("/?start=2026-04-01&end=2026-03-31")

    expect(page.locator(".errors")).to_contain_text("The start date 2026-04-01 is after the end date 2026-03-31.")
    expect(net_income(page)).to_have_count(0)


def test_the_check_is_collapsed_until_clicked(page: Page):
    page.goto(Q1)
    check = page.locator("details", has=page.locator("summary", has_text="Check: movement"))
    cash = check.locator("tr", has_text="1000 Cash")

    expect(cash).to_be_hidden()

    check.locator("summary").click()

    expect(cash).to_be_visible()
    expect(cash).to_contain_text("(52,007.07)")
    expect(check.locator("tr.subtotal")).to_contain_text("(44,480.14)")  # equals net income


def test_the_detail_lists_every_line_and_strikes_out_the_ones_not_counted(page: Page):
    page.goto(Q1)
    detail = page.locator("details", has=page.locator("summary", has_text="Detail: every journal line"))
    product_revenue = detail.locator("details", has=page.locator("summary", has_text="4000 Product Revenue"))
    void_line = product_revenue.locator("tr", has_text="JE-009")
    counted_line = product_revenue.locator("tr", has_text="JE-010")

    expect(product_revenue).to_be_hidden()  # the detail starts collapsed

    detail.locator("summary").first.click()

    expect(product_revenue.locator("summary")).to_have_text("4000 Product Revenue: 35,650.75")
    expect(void_line).to_be_hidden()  # and so does each account inside it

    product_revenue.locator("summary").click()

    expect(product_revenue.locator("tr.not-counted")).to_have_count(3)  # JE-001, JE-009, JE-024
    expect(void_line).to_contain_text("no, void")
    expect(void_line.locator("td").first).to_have_css("text-decoration-line", "line-through")
    expect(void_line.locator("td.reason")).to_have_css("text-decoration-line", "none")
    expect(counted_line.locator("td").first).to_have_css("text-decoration-line", "none")
    expect(product_revenue.locator("tr.subtotal")).to_contain_text("35,650.75")


def not_counted_reasons(page: Page) -> list[str]:
    """The reason shown on every struck-out line of the detail, open or collapsed."""
    return page.locator("tr.not-counted td.reason").all_text_contents()


def test_a_single_day_counts_only_that_day(page: Page):
    page.goto("/")
    page.get_by_label("Start date").fill("2026-03-31")
    page.get_by_label("End date").fill("2026-03-31")
    page.get_by_role("button", name="Show statement").click()

    # 2026-03-31 has three posted entries: subscription revenue 1,000.00 (JE-021),
    # payroll 18,500.00 (JE-022) and interest 42.18 (JE-023).
    expect(page.locator("tr", has_text="Net revenue")).to_contain_text("1,000.00")
    expect(page.locator("tr", has_text="Total operating expenses")).to_contain_text("18,500.00")
    expect(page.locator("tr", has_text="Total other income")).to_contain_text("42.18")
    expect(net_income(page)).to_have_text("(17,457.82)")  # 1,000.00 - 18,500.00 + 42.18
    expect(page.locator(".warnings")).to_have_count(0)  # the draft JE-019 is dated 2026-03-15

    # Of the 51 lines in the ledger, only the 6 lines of those three entries count.
    expect(page.locator("tr.counted")).to_have_count(6)
    expect(page.locator("tr.not-counted")).to_have_count(45)

    detail = page.locator("details", has=page.locator("summary", has_text="Detail: every journal line"))
    salaries = detail.locator("details", has=page.locator("summary", has_text="6000 Salaries"))
    detail.locator("summary").first.click()
    salaries.locator("summary").click()

    expect(salaries.locator("summary")).to_have_text("6000 Salaries: 18,500.00")
    expect(salaries.locator("tr.counted")).to_have_count(1)
    expect(salaries.locator("tr.counted")).to_contain_text("JE-022")
    expect(salaries.locator("tr", has_text="JE-006")).to_contain_text("no, outside the range")
    expect(salaries.locator("tr", has_text="JE-019")).to_contain_text("no, draft")


def test_a_very_large_range_includes_every_line_in_the_ledger(page: Page):
    page.goto("/?start=1900-01-01&end=2999-12-31")

    # Every posted entry: December 5,000.00, Q1 (44,480.14) and April 9,100.00.
    expect(page.locator("tr", has_text="Net revenue")).to_contain_text("51,950.50")
    expect(net_income(page)).to_have_text("(30,380.14)")
    expect(page.locator(".warnings")).to_contain_text("JE-019")

    # All 51 lines of the ledger are listed. Nothing is outside the range, so the only lines
    # not counted are the two lines each of the void JE-009 and JE-025 and the draft JE-019.
    expect(page.locator("tr.counted")).to_have_count(45)
    expect(page.locator("tr.not-counted")).to_have_count(6)
    assert sorted(not_counted_reasons(page)) == ["no, draft"] * 2 + ["no, void"] * 4
