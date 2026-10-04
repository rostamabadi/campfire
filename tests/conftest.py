"""Fixtures shared by the unit and integration tests."""

import pytest

from builders import LEDGER_PATH
from ledger import load_ledger


@pytest.fixture(scope="session")
def real_ledger():
    """ledger.json, loaded once for the whole test run."""
    return load_ledger(LEDGER_PATH)
