"""Record the take-home walkthrough video with Playwright.

It drives the real app in a headless browser and records one video, in four parts:
a demo, the code path from the dates to the numbers, how the numbers were checked, and
how it was built. Nothing on screen is mocked: the pages come from the app, the code is
read from the project files, and the terminal output is captured from the real commands.

Run it from the project folder, as a module, so that it can import the app:

    uv run python -m video.record_walkthrough

Pygments colours the code on screen. It is already installed, because pytest depends on it.

Settings, as environment variables:
    OUT          where the video goes. Default: the folder of this script
    CAPTIONS=0   record without the caption bar, for a voice-over
    SPEED=0.05   shorten every pause, for a quick dry run
    CICD_OUTPUT  a file with saved ./cicd.sh output, to skip running it again

It writes walkthrough.webm and timeline.md (each caption with its time in the video).
"""

import html
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_for_filename
from werkzeug.serving import BaseWSGIServer, make_server

from app import create_app

PROJECT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("OUT", Path(__file__).parent)).resolve()
CAPTIONS = os.environ.get("CAPTIONS", "1") != "0"
SPEED = float(os.environ.get("SPEED", "1"))

WIDTH, HEIGHT = 1920, 1080
ZOOM = 1.5          # the app page is shown at 150%, like Cmd-plus in a browser
TOP = 56            # height of the address bar on app pages and of the file tab on code pages
CAPTION = 132       # height of the caption bar
WORDS_PER_SECOND = 2.5

MONO = "ui-monospace, SFMono-Regular, Menlo, monospace"

# Added to every app page before it renders: the zoom, an address bar (the recording has no
# browser window around it), a mouse pointer, and a box to point at things. The pointer's
# position is kept in window.name, which survives a navigation.
INIT_JS = """
(() => {
  if (!location.protocol.startsWith('http')) return;
  const style = document.createElement('style');
  style.textContent = `
    html { padding-top: %(top)spx; }
    body { zoom: %(zoom)s; padding-bottom: 120px !important; }
    #wt-root { position: absolute; top: 0; left: 0; width: 0; height: 0; z-index: 99990; }
    #wt-address { position: fixed; top: 0; left: 0; width: 100vw; height: %(top)spx; box-sizing: border-box;
      background: #eef0f3; border-bottom: 1px solid #cfd4da; display: flex; align-items: center;
      justify-content: center; }
    #wt-address span { width: 1056px; box-sizing: border-box; background: #fff; border: 1px solid #cfd4da;
      border-radius: 19px; padding: 7px 20px; font: 19px %(mono)s; color: #1f2328; white-space: nowrap;
      overflow: hidden; text-overflow: ellipsis; }
    #wt-spot { position: absolute; box-sizing: border-box; border: 4px solid #f08c00; border-radius: 8px;
      box-shadow: 0 0 0 7px rgba(240, 140, 0, .16); pointer-events: none; opacity: 0;
      transition: left .35s ease, top .35s ease, width .35s ease, height .35s ease, opacity .25s ease; }
    #wt-cursor { position: fixed; width: 30px; height: 30px; margin: -3px 0 0 -7px; pointer-events: none;
      transition: left .6s cubic-bezier(.3, .1, .2, 1), top .6s cubic-bezier(.3, .1, .2, 1); z-index: 99999; }
    #wt-ripple { position: fixed; width: 44px; height: 44px; margin: -22px 0 0 -22px; border-radius: 50%%;
      background: rgba(240, 140, 0, .55); pointer-events: none; opacity: 0; z-index: 99998; }
    #wt-ripple.go { animation: wt-ripple .45s ease-out; }
    @keyframes wt-ripple { from { opacity: .9; transform: scale(.3); } to { opacity: 0; transform: scale(1.7); } }
  `;
  // The script runs before the page has any element, so wait for the first one.
  const addStyle = () => (document.head || document.documentElement).appendChild(style);
  if (document.documentElement) addStyle();
  else new MutationObserver((_, observer) => {
    if (document.documentElement) { observer.disconnect(); addStyle(); }
  }).observe(document, { childList: true });

  const state = (() => { try { return JSON.parse(window.name); } catch (e) { return null; } })() || { x: 1500, y: 420 };
  const save = () => { window.name = JSON.stringify(state); };

  const wt = window.wt = {
    top: %(top)s,
    bottom: () => innerHeight - %(caption)s,
    move(x, y) {
      state.x = x; state.y = y; save();
      const cursor = document.getElementById('wt-cursor');
      cursor.style.left = x + 'px'; cursor.style.top = y + 'px';
    },
    ripple() {
      const ripple = document.getElementById('wt-ripple');
      ripple.style.left = state.x + 'px'; ripple.style.top = state.y + 'px';
      ripple.classList.remove('go'); void ripple.offsetWidth; ripple.classList.add('go');
    },
    // Scroll so that the box from `first` to `last` sits in the visible area, if it does not already.
    reveal(first, last, always) {
      const a = first.getBoundingClientRect(), b = (last || first).getBoundingClientRect();
      const top = Math.min(a.top, b.top), bottom = Math.max(a.bottom, b.bottom);
      const room = wt.bottom() - wt.top;
      if (!always && top >= wt.top + 16 && bottom <= wt.bottom() - 16) return false;
      const gap = Math.max(24, Math.min((room - (bottom - top)) / 2, 220));
      window.scrollTo({ top: Math.max(0, scrollY + top - wt.top - gap), behavior: 'smooth' });
      return true;
    },
    spot(first, last, pad) {
      const a = first.getBoundingClientRect(), b = (last || first).getBoundingClientRect();
      const left = Math.min(a.left, b.left), top = Math.min(a.top, b.top);
      const right = Math.max(a.right, b.right), bottom = Math.max(a.bottom, b.bottom);
      const spot = document.getElementById('wt-spot');
      spot.style.left = (left + scrollX - pad) + 'px';
      spot.style.top = (top + scrollY - pad) + 'px';
      spot.style.width = (right - left + 2 * pad) + 'px';
      spot.style.height = (bottom - top + 2 * pad) + 'px';
      spot.style.opacity = 1;
    },
    unspot() { document.getElementById('wt-spot').style.opacity = 0; },
  };

  document.addEventListener('DOMContentLoaded', () => {
    const root = document.createElement('div');
    root.id = 'wt-root';
    root.innerHTML = `
      <div id="wt-spot"></div>
      <div id="wt-address"><span></span></div>
      <div id="wt-ripple"></div>
      <svg id="wt-cursor" viewBox="0 0 24 24"><path d="M5 2l14 11.5h-7.2l4 8.3-2.8 1.3-4-8.4L5 19z"
        fill="#111" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>`;
    document.documentElement.appendChild(root);
    if (document.contentType === 'application/json') {
      style.textContent += 'body { margin: 10px 0 0 288px; } pre { font-size: 15px; line-height: 1.35; }';
    }
    root.querySelector('#wt-address span').textContent = location.host + location.pathname + location.search;
    const cursor = root.querySelector('#wt-cursor');
    cursor.style.transition = 'none';
    cursor.style.left = state.x + 'px'; cursor.style.top = state.y + 'px';
    requestAnimationFrame(() => requestAnimationFrame(() => { cursor.style.transition = ''; }));
  });
})();
"""

CODE_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>%(name)s</title>
<style>
  html { background: #fff; }
  body { margin: 0; }
  header { position: fixed; top: 0; left: 0; right: 0; height: %(top)spx; box-sizing: border-box; z-index: 5;
    background: #eef0f3; border-bottom: 1px solid #cfd4da; display: flex; align-items: flex-end; padding-left: 28px; }
  header .tab { background: #fff; border: 1px solid #cfd4da; border-bottom: 0; border-radius: 9px 9px 0 0;
    padding: 9px 24px 10px; margin-bottom: -1px; font: 600 19px %(mono)s; color: #1f2328; }
  header .folder { align-self: center; margin-left: auto; margin-right: 28px; font: 17px %(mono)s; color: #6b7280; }
  .highlight { background: #fff; }
  .highlight pre { margin: 0; padding: %(pad)spx 0 1200px; font: 19px/28px %(mono)s; counter-reset: line; }
  span[id^="L-"] { display: block; border-left: 6px solid transparent; transition: opacity .3s, background .3s; }
  span[id^="L-"]::before { counter-increment: line; content: counter(line); display: inline-block; width: 62px;
    margin-right: 22px; text-align: right; color: #9aa0a6; }
  pre.focus span[id^="L-"] { opacity: .3; }
  pre.focus span[id^="L-"].hl { opacity: 1; background: #fff4cc; border-left-color: #f08c00; }
  %(pygments)s
</style>
<header><span class="tab">%(name)s</span><span class="folder">%(folder)s</span></header>
%(code)s
<script>
  // Mark lines first..last, dim the rest, and bring them into the space between the tab and the caption.
  window.focusLines = (first, last, smooth) => {
    document.querySelector('pre').classList.add('focus');
    document.querySelectorAll('.hl').forEach(line => line.classList.remove('hl'));
    for (let n = first; n <= last; n++) document.getElementById('L-' + n).classList.add('hl');
    const a = document.getElementById('L-' + first).getBoundingClientRect();
    const b = document.getElementById('L-' + last).getBoundingClientRect();
    const room = innerHeight - %(caption)s - %(top)s;
    const gap = Math.max(28, Math.min((room - (b.bottom - a.top)) / 2, 168));
    window.scrollTo({ top: Math.max(0, scrollY + a.top - %(top)s - gap), behavior: smooth ? 'smooth' : 'instant' });
  };
</script>
"""

TERMINAL_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>%(command)s</title>
<style>
  html { background: #16181d; }
  body { margin: 0; }
  header { position: fixed; top: 0; left: 0; right: 0; height: %(top)spx; box-sizing: border-box; z-index: 5;
    background: #2a2d34; border-bottom: 1px solid #3a3e47; display: flex; align-items: center; padding-left: 28px;
    font: 600 19px %(mono)s; color: #c9d1d9; }
  pre { margin: 0; padding: %(pad)spx 40px %(bottom)spx; font: 19px/27px %(mono)s; color: #d7dce2;
    white-space: pre-wrap; }
  .prompt { color: #7ee787; }
  .ok { color: #7ee787; }
</style>
<header>Terminal</header>
<pre><span class="prompt">$</span> %(command)s
%(output)s</pre>
"""


def serve(ledger: Path | None, port: int) -> tuple[BaseWSGIServer, str]:
    """Start the app on `port`, or on a free port if that one is taken. Returns (server, address)."""
    app = create_app(ledger)
    # Indented JSON, so that the API response can be read on screen. Only the whitespace differs.
    app.json.compact = False
    try:
        server = make_server("127.0.0.1", port, app)
    except (OSError, SystemExit):
        server = make_server("127.0.0.1", 0, app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def source_lines(name: str) -> list[str]:
    return (PROJECT / name).read_text().splitlines()


def line_of(name: str, text: str, after: int = 1) -> int:
    """The number of the first line of the file, from line `after` on, that contains `text`."""
    for number, line in enumerate(source_lines(name), start=1):
        if number >= after and text in line:
            return number
    sys.exit(f"'{text}' was not found in {name} from line {after} on. Update the marker in this script.")


def code_page(pages: Path, name: str) -> Path:
    """Write the HTML page that shows one project file with line numbers, and return its path."""
    target = pages / (name.replace("/", "__") + ".html")
    if not target.exists():
        formatter = HtmlFormatter(linespans="L", style="xcode")
        lexer = get_lexer_for_filename(name, stripnl=False)
        target.write_text(CODE_PAGE % {
            "name": html.escape(name),
            "folder": html.escape(PROJECT.name),
            "top": TOP,
            "pad": TOP + 16,
            "caption": CAPTION,
            "mono": MONO,
            "pygments": formatter.get_style_defs(".highlight"),
            "code": highlight((PROJECT / name).read_text(), lexer, formatter),
        })
    return target


def terminal_page(pages: Path, slug: str, command: str, output: str) -> Path:
    """Write the HTML page that shows a command and the output it really printed."""
    text = html.escape(output.rstrip("\n"))
    text = re.sub(r"^(caught  |All checks passed[.!]|All tests passed\.|.*\bpassed in .*|Success: .*)",
                  r'<span class="ok">\1</span>', text, flags=re.MULTILINE)
    target = pages / f"{slug}.html"
    target.write_text(TERMINAL_PAGE % {
        "command": html.escape(command), "output": text, "top": TOP, "pad": TOP + 20, "bottom": CAPTION + 40,
        "mono": MONO,
    })
    return target


def run(command: list[str]) -> str:
    """Run a command in the project and return what it printed, without colour codes."""
    result = subprocess.run(command, cwd=PROJECT, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"{' '.join(command)} failed:\n{result.stdout}{result.stderr}")
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


class Take:
    """One recording: the page, the caption on screen, and the running time."""

    def __init__(self, page: Page, pages: Path):
        self.page = page
        self.pages = pages          # the folder for the code and terminal pages made along the way
        self.caption = None         # the overlay now on screen
        self.caption_until = 0.0    # planned time until which the current caption should stay
        self.planned = 0.0          # seconds of video so far, as planned (pauses only)
        self.started = time.monotonic()
        self.timeline: list[tuple[float, float, str]] = []  # (planned, actual, text)

    # --- time

    def pause(self, seconds: float) -> None:
        self.planned += seconds
        self.page.wait_for_timeout(max(seconds * SPEED * 1000, 1))

    def rest(self) -> None:
        """Wait until the caption on screen has been up long enough to read aloud."""
        if self.planned < self.caption_until:
            self.pause(self.caption_until - self.planned)

    # --- captions

    def say(self, text: str) -> None:
        """Replace the caption. The one before it is first given its full reading time."""
        self.rest()
        self.timeline.append((self.planned, time.monotonic() - self.started, text))
        self.caption_until = self.planned + len(text.split()) / WORDS_PER_SECOND + 0.9
        if not CAPTIONS:
            return
        bar = (
            f'<div style="position:fixed;left:0;right:0;bottom:0;height:{CAPTION}px;box-sizing:border-box;'
            f"display:flex;align-items:center;justify-content:center;padding:0 110px;text-align:center;"
            f'background:#12151c;color:#fff;font:500 31px/1.34 system-ui,sans-serif;">{html.escape(text)}</div>'
        )
        previous = self.caption
        self.caption = self.page.screencast.show_overlay(bar)
        if previous is not None:
            previous.__exit__(None, None, None)  # the overlay is a context manager: leaving it removes it

    def chapter(
        self, title: str, description: str, seconds: float = 2.4, behind: Callable[[], None] | None = None
    ) -> None:
        """Show a title card. `behind` puts the next view on screen first, so the card opens onto it."""
        self.rest()
        if self.caption is not None:
            self.caption.__exit__(None, None, None)
            self.caption = None
        if behind is not None:
            behind()
        self.timeline.append((self.planned, time.monotonic() - self.started, f"[{title}]"))
        self.planned += seconds
        self.page.screencast.show_chapter(title, description=description, duration=max(seconds * SPEED, 0.3) * 1000)
        self.page.wait_for_timeout(250)

    # --- the app pages

    def goto(self, address: str) -> None:
        self.page.goto(address)
        self.pause(0.6)

    def reveal(self, first: Locator, last: Locator | None = None, always: bool = False) -> None:
        """Scroll until the box from `first` to `last` is in view."""
        handles = [first.element_handle(), last.element_handle() if last else None]
        if self.page.evaluate("([a, b, always]) => wt.reveal(a, b, always)", [*handles, always]):
            self.pause(0.9)

    def spot(self, first: Locator, last: Locator | None = None, pad: int = 6) -> None:
        """Draw the box around everything from `first` to `last`, scrolling to it if needed."""
        self.reveal(first, last)
        handles = [first.element_handle(), last.element_handle() if last else None]
        self.page.evaluate("([a, b, pad]) => wt.spot(a, b, pad)", [*handles, pad])
        self.pause(0.5)

    def unspot(self) -> None:
        self.page.evaluate("wt.unspot()")

    def point(self, target: Locator) -> None:
        """Move the pointer onto the element."""
        self.reveal(target)
        box = target.bounding_box()
        if box is None:
            sys.exit(f"Nothing to point at: {target}")
        self.page.evaluate("([x, y]) => wt.move(x, y)", [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2])
        self.pause(0.75)

    def click(self, target: Locator, navigates: bool = False) -> None:
        self.point(target)
        self.page.evaluate("wt.ripple()")
        self.pause(0.3)
        if navigates:
            with self.page.expect_navigation():
                target.click()
        else:
            target.click()
        self.pause(0.6)

    def fill(self, target: Locator, value: str) -> None:
        self.click(target)
        target.fill(value)
        self.pause(0.5)

    def scroll(self, top: int | str) -> None:
        self.page.evaluate(f"window.scrollTo({{ top: {top}, behavior: 'smooth' }})")
        self.pause(1.0)

    # --- the code and terminal pages

    def code(self, name: str, first_text: str, last_text: str) -> None:
        """Show a project file with the lines from `first_text` to `last_text` marked."""
        first = line_of(name, first_text)
        last = line_of(name, last_text, after=first)
        address = code_page(self.pages, name).as_uri()
        arriving = self.page.url != address
        if arriving:
            self.page.goto(address)
        self.page.evaluate("([a, b, smooth]) => focusLines(a, b, smooth)", [first, last, not arriving])
        self.pause(0.5 if arriving else 1.0)

    def terminal(self, slug: str, command: str, output: str) -> None:
        self.page.goto(terminal_page(self.pages, slug, command, output).as_uri())
        self.pause(0.6)


def record(take: Take, main: str, with_warnings: str, with_errors: str, cicd: str, history: str) -> None:
    page = take.page
    statement = page.locator("body > table")
    start, end = page.get_by_label("Start date"), page.get_by_label("End date")
    show = page.get_by_role("button", name="Show statement")

    def row(text: str) -> Locator:
        return statement.locator("tr", has_text=text)

    take.chapter("Income statement", "Northwind Coffee Roasters. Demo, code path, checks, how it was built.", 2.6)

    # ---- 1. Demo

    take.say("The page opens on the whole ledger, from the first posted entry to the last.")
    take.spot(page.locator("h2 + p"))

    take.say("Q1 2026, January 1 to March 31. Both days are included.")
    take.unspot()
    take.fill(start, "2026-01-01")
    take.fill(end, "2026-03-31")
    take.click(show, navigates=True)
    take.spot(page.locator("h2 + p"))

    take.say("A draft dated inside the range is shown as a note and left out of the totals.")
    take.spot(page.locator(".warnings"))

    take.say("Returns and discounts are contra revenue: a negative line, so the subtotal is net revenue.")
    take.spot(row("4900 Sales Returns"), row("Net revenue"))

    take.say("The vendor credit lowers Software to 1,099.97. The inactive Marketing account keeps its history.")
    take.spot(row("6200 Software"), row("6300 Marketing"))

    take.say("Net income for Q1 is (44,480.14), a net loss. It matches the figure worked out by hand.")
    take.spot(row("Net income"))

    take.say("The control total: the balance-sheet accounts moved by the same amount. "
             "The app checks this on every request.")
    check = page.locator("body > details").nth(0)
    take.unspot()
    take.click(check.locator("summary").first)
    take.reveal(row("Net income"), check.locator("tr.subtotal"), always=True)
    take.spot(check.locator("tr.subtotal"))

    take.say("The detail lists every journal line by account. Lines that do not count are struck out, "
             "with the reason.")
    detail = page.locator("body > details").nth(1)
    take.unspot()
    take.click(detail.locator("summary").first)
    product = detail.locator("details.account-detail", has_text="4000 Product Revenue")
    take.click(product.locator("summary"))
    take.reveal(product, always=True)

    take.say("Product Revenue: December and April are outside the range, JE-009 is void. "
             "The rest add up to 35,650.75.")
    take.spot(product.locator("table"))

    take.say("Any range works. January alone is a loss of 21,529.65, with three months of rent, as recorded.")
    take.unspot()
    take.scroll(0)
    take.fill(end, "2026-01-31")
    take.click(show, navigates=True)
    take.spot(row("6100 Rent"))
    take.pause(1.6)
    take.spot(row("Net income"))

    take.say("A start date after the end date gives an error, and no statement.")
    take.unspot()
    take.scroll(0)
    take.fill(start, "2026-04-01")
    take.click(show, navigates=True)
    take.spot(page.locator(".errors"))

    take.say("The API returns the same statement as JSON. Amounts are decimal strings, never floats.")
    take.goto(main + "/income-statement?start=2026-01-01&end=2026-03-31")

    take.say("It carries the control total and the warnings too.")
    take.scroll("document.documentElement.scrollHeight")

    take.say("A sample ledger with bad data in draft and void entries. The statement is shown, with notes.")
    take.goto(with_warnings + "/")
    take.spot(page.locator(".warnings"))

    take.say("Bad data in the accounts or in a posted entry could change the totals. "
             "Every problem is listed, and no numbers.")
    take.goto(with_errors + "/")
    take.spot(page.locator(".errors p"))
    take.pause(2.0)
    take.unspot()
    take.scroll(620)

    # ---- 2. The code path

    take.chapter(
        "The code path", "From the two dates to the numbers.",
        behind=lambda: take.code("app.py", '@app.get("/income-statement")', "return statement_json(statement)"),
    )
    take.say("Both routes do the same: read the ledger, then build the statement for the dates "
             "in the query string.")

    take.say("The file is read and checked on every request.")
    take.code("app.py", "def read_ledger()", "return None, failure.errors")

    take.say("A problem in a posted entry is an error. In a draft or void entry it is a warning, "
             "and the entry is left out.")
    take.code("ledger.py", "for position, raw in enumerate(", "raise LedgerError(errors)")

    take.say("Amounts go from the JSON strings straight into Decimal, never through float.")
    take.code("ledger.py", "lines = [", "for raw_line in raw[")

    take.say("The two dates are parsed. A missing, invalid or reversed range is a 400 error.")
    take.code("app.py", "def parse_range(", "return dates.get(")

    take.say("income_statement defines the four sections once: heading, subtotal label, subtypes and sign.")
    take.code("statement.py", "def income_statement(", "gross_profit, operating_income, net_income = results(")

    take.say("A line counts when its entry is posted and dated inside the range.")
    take.code("statement.py", "def entries_in_range(", "    ]")

    take.say("Every journal line is listed under its account, with whether it counts and why not.")
    take.code("statement.py", "def detail_lines_by_account(", "return lines_by_account")

    take.say("An account's amount is the sum of its counted lines. The sign comes only from the section.")
    take.code("statement.py", "lines = []", "return Section(")

    take.say("Three subtotals, then the control total. If the two figures differ, there is an error "
             "and no statement.")
    take.code("statement.py", "gross_profit, operating_income, net_income = results(", "))")

    take.say("Money is formatted at the edge: plain strings in JSON, separators and parentheses on the page.")
    take.code("app.py", "def money(", 'return f"{amount:,.2f}"')

    # ---- 3. How the numbers were checked

    take.chapter(
        "The checks", "How the numbers were checked.",
        behind=lambda: take.code("tests/integration/test_real_ledger.py", "def test_q1_2026_every_line_and_subtotal(",
                                 "assert statement.net_income =="),
    )
    take.say("Expected values are worked out by hand from ledger.json. The comments show the working.")

    take.say("Invariants over many date ranges: net income equals the balance-sheet movement, "
             "and adjacent ranges add up.")
    take.code("tests/integration/test_real_ledger.py",
              "def test_net_income_equals_the_net_movement_in_balance_sheet_accounts(",
              "assert income_statement(real_ledger, start, end).net_income == net_debits")

    take.say("The mutation check plants 20 mistakes, one at a time, and confirms the tests fail for each.")
    take.code("tests/mutation_check.py", "MISTAKES = [", '"contra revenue is forced positive"')

    take.say("cicd.sh runs lint, types, every test and the mutation check.")
    take.terminal("cicd", "./cicd.sh", cicd)
    take.pause(1.8)
    take.scroll("document.documentElement.scrollHeight")

    # ---- 4. How it was built

    take.chapter(
        "How it was built", "The tools, and how they were used.",
        behind=lambda: take.code("NOTES.md", "## Where AI helped", "Claude Code helped read the brief"),
    )
    take.say("Claude Code helped read the brief, list the traps in the data, and write the code and tests.")

    take.say("CLAUDE.md holds the decisions it works from, and the working agreements.")
    take.code("CLAUDE.md", "## Priorities", "- Every income-statement account always gets a line")
    take.pause(2.2)
    take.code("CLAUDE.md", "## Working agreements", "- When a fact changes")

    take.say("Changes are made on branches and merged through pull requests, without squashing.")
    take.terminal("history", "git log --graph --oneline", history)

    take.say("Where the AI was wrong is logged in NOTES.md. Tests that pass first time prove little, "
             "so mistakes are planted.")
    take.code("NOTES.md", "## Where AI helped", "- **Not trusted:**")

    take.chapter("Q1 2026 net income: (44,480.14)", "README.md has the commands. NOTES.md has the decisions.", 3.0)


def main() -> None:
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    OUT.mkdir(parents=True, exist_ok=True)

    saved = os.environ.get("CICD_OUTPUT")
    if saved:
        cicd = re.sub(r"\x1b\[[0-9;]*m", "", Path(saved).read_text())
    else:
        print("Running ./cicd.sh for its output. This takes a minute...")
        cicd = run(["./cicd.sh"])
    cicd = "\n".join(line for line in cicd.splitlines() if not line.startswith("exit="))
    history = "\n".join(run(["git", "log", "--graph", "--oneline", "-n", "12"]).splitlines()[:30])

    # The real ledger, then the two sample ledgers that hold the bad data.
    servers = []
    addresses = []
    ledgers = [None, PROJECT / "tests/data/ledger_warnings.json", PROJECT / "tests/data/ledger_blocking_errors.json"]
    for port, ledger in zip((5001, 5002, 5003), ledgers, strict=True):
        server, address = serve(ledger, port)
        servers.append(server)
        addresses.append(address)

    video = OUT / "walkthrough.webm"
    with sync_playwright() as playwright, tempfile.TemporaryDirectory() as pages:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT})
        context.add_init_script(INIT_JS % {"top": TOP, "zoom": ZOOM, "caption": CAPTION, "mono": MONO})
        page = context.new_page()
        page.on("pageerror", lambda error: print(f"Error on the page: {error}"))
        page.goto(addresses[0] + "/")

        take = Take(page, Path(pages))
        page.screencast.start(path=str(video), size={"width": WIDTH, "height": HEIGHT}, quality=92)
        take.started = time.monotonic()
        record(take, *addresses, cicd, history)
        actual = time.monotonic() - take.started
        page.screencast.stop()
        context.close()
        browser.close()

    for server in servers:
        server.shutdown()

    lines = ["# Walkthrough timeline", "", "| Time | On screen |", "| --- | --- |"]
    for planned, real, text in take.timeline:
        at = real if SPEED == 1 else planned
        lines.append(f"| {int(at // 60)}:{int(at % 60):02d} | {text} |")
    (OUT / "timeline.md").write_text("\n".join(lines) + "\n")

    words = sum(len(text.split()) for _, _, text in take.timeline if not text.startswith("["))
    print(json.dumps({
        "video": str(video),
        "megabytes": round(video.stat().st_size / 1e6, 1),
        "captions": len(take.timeline),
        "words": words,
        "planned_seconds": round(take.planned),
        "recorded_seconds": round(actual),
    }, indent=2))


if __name__ == "__main__":
    main()
