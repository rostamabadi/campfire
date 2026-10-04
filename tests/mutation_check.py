"""Break one rule at a time and confirm that the tests notice.

For each mistake below, the project is copied to a temporary folder, one piece of correct
code is replaced by a wrong version, and the tests are run against the copy. They must
fail. A mistake that survives is one the tests would let through.

Run with: uv run python tests/mutation_check.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
COPIED = ["ledger.json", "ledger.py", "statement.py", "app.py", "templates", "tests", "pyproject.toml"]

# (the mistake, the file, the correct code, the wrong code)
MISTAKES = [
    (
        "drafts are counted",
        "statement.py",
        "if entry.status == status and start <= entry.date <= end",
        'if entry.status in (status, "draft") and start <= entry.date <= end',
    ),
    (
        "the end date is left out of the range",
        "statement.py",
        "start <= entry.date <= end",
        "start <= entry.date < end",
    ),
    (
        "the start date is left out of the range",
        "statement.py",
        "start <= entry.date <= end",
        "start < entry.date <= end",
    ),
    (
        "expenses are the sum of debits, ignoring credits",
        "statement.py",
        "amount = credits - debits if credit_normal else debits - credits",
        "amount = credits - debits if credit_normal else debits",
    ),
    (
        "contra revenue is forced positive",
        "statement.py",
        "amount = credits - debits if credit_normal else debits - credits",
        "amount = abs(credits - debits) if credit_normal else debits - credits",
    ),
    (
        "other income is also counted inside revenue",
        "statement.py",
        '["operating_revenue", "contra_revenue"], credit_normal=True',
        '["operating_revenue", "contra_revenue", "other_income"], credit_normal=True',
    ),
    (
        "inactive accounts are dropped",
        "statement.py",
        "if account.subtype == subtype]",
        "if account.subtype == subtype and account.is_active]",
    ),
    (
        "gross profit adds cost of goods sold",
        "statement.py",
        "revenue.total - cost_of_goods_sold.total",
        "revenue.total + cost_of_goods_sold.total",
    ),
    (
        "other income is subtracted",
        "statement.py",
        "operating_income + other_income.total",
        "operating_income - other_income.total",
    ),
    (
        "the control total is switched off",
        "statement.py",
        "if balance_sheet_movement.total != net_income:",
        "if False:",
    ),
    (
        "a void twin is flagged as a possible duplicate",
        "statement.py",
        'for entry in entries_in_range(ledger, start, end, "posted"):',
        'for entry in [e for e in ledger.entries if e.status != "draft" and start <= e.date <= end]:',
    ),
    (
        "drafts in the range are not reported",
        "statement.py",
        'for entry in entries_in_range(ledger, start, end, "draft"):',
        "for entry in []:",
    ),
    (
        "the detail shows every line as counted",
        "statement.py",
        'counted=reason == "",',
        "counted=True,",
    ),
    (
        "amounts pass through float",
        "ledger.py",
        "amount = Decimal(text)",
        "amount = Decimal(float(text))",
    ),
    (
        "JSON numbers are accepted as amounts",
        "ledger.py",
        "if not isinstance(text, str):",
        "if False:",
    ),
    (
        "unbalanced entries are accepted",
        "ledger.py",
        "if amounts_are_valid and total_debits != total_credits:",
        "if False:",
    ),
    (
        "a revenue account filed as balance_sheet is accepted",
        "ledger.py",
        "if subtype not in allowed:",
        "if False:",
    ),
    (
        "a problem in a draft blocks the statement",
        "ledger.py",
        'elif raw.get("status") in ("draft", "void"):',
        "elif False:",
    ),
    (
        "JSON amounts are numbers, not strings",
        "app.py",
        'return f"{amount:.2f}"',
        "return float(amount)",
    ),
    (
        "a start date after the end date is accepted",
        "app.py",
        'if not errors and dates["start"] > dates["end"]:',
        "if False:",
    ),
]


def tests_catch(file: str, correct: str, wrong: str) -> bool:
    """Copy the project, plant the mistake, run the tests. True if they fail."""
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder)
        for name in COPIED:
            source = ROOT / name
            if source.is_dir():
                shutil.copytree(source, copy / name, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy(source, copy / name)

        target = copy / file
        text = target.read_text()
        if text.count(correct) != 1:
            sys.exit(f"Expected this code exactly once in {file}, found it {text.count(correct)} times:\n{correct}")
        target.write_text(text.replace(correct, wrong))

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
            cwd=copy,
            capture_output=True,
            text=True,
        )
        # 0 is "all passed" and 1 is "some failed". Anything else means the tests did not run.
        if result.returncode not in (0, 1):
            sys.exit(f"The tests could not run with this mistake planted in {file}:\n{result.stdout}{result.stderr}")
        return result.returncode == 1


def main():
    survivors = []
    for mistake, file, correct, wrong in MISTAKES:
        caught = tests_catch(file, correct, wrong)
        print(f"{'caught  ' if caught else 'SURVIVED'}  {mistake}")
        if not caught:
            survivors.append(mistake)

    print(f"\nThe tests caught {len(MISTAKES) - len(survivors)} of {len(MISTAKES)} mistakes.")
    sys.exit(1 if survivors else 0)


if __name__ == "__main__":
    main()
