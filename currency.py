"""Show a statement in another currency.

The ledger is in US dollars. The rules, in one place:
- A rate is what one dollar is worth in the other currency: at 0.9, 100.00 USD is 90.00 EUR.
  One rate applies to the whole range.
- Each account line is converted once, and rounded half up to the cent.
- Every subtotal and result is added up from the converted lines, so the statement still
  adds up. Converting each total on its own could leave them a cent apart.
- The control total and the detail under each line are not converted. They describe the
  ledger as recorded, and the control total is only exact there.
"""

import re
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Context, Decimal

from statement import ZERO, IncomeStatement, Section, results

BASE_CURRENCY = "USD"  # the default rates below are per US dollar


@dataclass(frozen=True)
class Currency:
    code: str  # such as "EUR"
    name: str  # such as "Euro"
    default_rate: Decimal  # what one US dollar is worth in this currency


# The currencies a statement can be converted to. A new one is one more line here.
CURRENCIES = [
    Currency("EUR", "Euro", Decimal("0.9")),
    Currency("GBP", "Pound", Decimal("0.7")),
]

CENT = Decimal("0.01")
RATE_LIMIT = Decimal("1000000")
# Decimal keeps 28 digits unless told otherwise. An amount times a rate can need more, so
# the product is worked out with 50 digits, which is exact, and only then rounded to the cent.
WIDE = Context(prec=50)


def parse_rate(text: str) -> Decimal | None:
    """Return the rate for a plain decimal string such as "0.9", or None if it is not a valid rate.

    A valid rate is written with digits only, has at most six decimal places, and is above
    zero and below RATE_LIMIT.
    """
    if not re.fullmatch(r"[0-9]+(\.[0-9]{1,6})?", text):
        return None
    rate = Decimal(text)
    if rate <= 0 or rate >= RATE_LIMIT:
        return None
    return rate


def convert(amount: Decimal, rate: Decimal) -> Decimal:
    """The amount in the other currency: the amount times the rate, rounded half up to the cent.

    Half a cent is rounded away from zero, so a negative amount converts to the same figure
    as the positive one, with a minus sign.
    """
    converted = WIDE.multiply(amount, rate).quantize(CENT, rounding=ROUND_HALF_UP, context=WIDE)
    # A small negative amount rounds to "-0.00". Zero has no sign on a statement.
    return ZERO if converted == 0 else converted


def convert_section(section: Section, rate: Decimal) -> Section:
    """The section with each line converted, and a total added up from the converted lines."""
    lines = [replace(line, amount=convert(line.amount, rate)) for line in section.lines]
    return replace(section, lines=lines, total=sum((line.amount for line in lines), ZERO))


def convert_statement(statement: IncomeStatement, currency: str, rate: Decimal) -> IncomeStatement:
    """The statement in another currency. `statement` is as recorded, in the ledger's currency.

    Only the amounts on the statement change: the lines of the four sections, their totals
    and the three results. The control total and the detail under each line stay as recorded.
    """
    revenue, cost_of_goods_sold, operating_expenses, other_income = (
        convert_section(section, rate) for section in statement.sections
    )
    gross_profit, operating_income, net_income = results(revenue, cost_of_goods_sold, operating_expenses, other_income)

    return replace(
        statement,
        currency=currency,
        rate=rate,
        revenue=revenue,
        cost_of_goods_sold=cost_of_goods_sold,
        gross_profit=gross_profit,
        operating_expenses=operating_expenses,
        operating_income=operating_income,
        other_income=other_income,
        net_income=net_income,
    )
