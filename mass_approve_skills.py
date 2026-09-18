"""
Mass Approve/Reject Skill and Certification Ratings via Playwright
=================================================================
Reads the Manager Tracker CSV export, then drives the Salesforce
Mass Approve Skills and Certification page in org62.

The page uses a Bryntum grid inside Shadow DOM — all grid interaction
uses JavaScript evaluation following the same pattern as scrape_skill_ratings.py.

Pass 1 – Approve all rows where Final Action == "Approve" (en masse,
         single comment).
Pass 2 – Reject rows where Final Action == "Reject" one at a time,
         using Discussion Notes as the reject comment (max 4000 chars).

Run:
    python3 mass_approve_skills.py

Results are written to mass_approve_results.json in the same directory.
"""

import csv
import datetime
import json
import shutil
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

# Timestamp stamped on every screenshot filename for this process invocation
_RUN_TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

CSV_PATH = (
    Path.home()
    / "Downloads"
    / "skill_rating_review.xlsx - Manager Tracker.csv"
)
RESULTS_PATH = Path(__file__).parent / "mass_approve_results.json"
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
MASS_APPROVE_URL = (
    "https://org62.lightning.force.com/lightning/n/Mass_Approve_Skills_and_Certification"
)
APPROVE_COMMENT = "Reviewed and approved by PL, Alexis Williams."
MAX_COMMENT_CHARS = 4000

# Column IDs used by the Bryntum grid on the Mass Approve page
_COL_EMPLOYEE = "col-pse__resource__r_name"
_COL_SKILL = "col-pse__skill_certification__r_name"

# ---------------------------------------------------------------------------
# JS constants (shadow-DOM aware)
# ---------------------------------------------------------------------------

# Traverses shadow roots to locate an element matching `sel`.
_FIND_EL_FN = """
function findEl(root, sel) {
    const found = root.querySelector(sel);
    if (found) return found;
    for (const el of root.querySelectorAll('*')) {
        if (el.shadowRoot) {
            const r = findEl(el.shadowRoot, sel);
            if (r) return r;
        }
    }
    return null;
}
"""

# Waits for the Bryntum host to appear anywhere in the shadow tree.
_WAIT_FOR_GRID_JS = (
    "() => { "
    + _FIND_EL_FN
    + " return !!findEl(document, 'c-bryntum-widget-host'); }"
)

# Collects all visible rows and their cell data from the grid, scrolling to get
# virtual rows.  Returns [{id, col-pse__resource__r_name, col-pse__skill_certification__r_name, ...}].
_GET_ALL_ROWS_JS = (
    "async () => { "
    + _FIND_EL_FN
    + """
    const host = findEl(document, 'c-bryntum-widget-host');
    if (!host) return { error: 'no-host' };
    const sr = host.shadowRoot;
    const scroller = sr.querySelector('.b-grid-body-container');
    if (!scroller) return { error: 'no-scroller' };

    function collectRows() {
        return [...sr.querySelectorAll('.b-grid-row')].map(row => {
            const record = { id: row.dataset.id };
            for (const cell of row.querySelectorAll('.b-grid-cell')) {
                const col = cell.dataset.columnId;
                if (col) record[col] = cell.textContent?.trim() ?? '';
            }
            return record;
        });
    }

    const seen = new Map();
    collectRows().forEach(r => { if (r.id) seen.set(r.id, r); });

    const totalHeight = scroller.scrollHeight;
    const step = Math.max(scroller.clientHeight, 100);
    let pos = step;
    while (pos <= totalHeight + step) {
        scroller.scrollTop = pos;
        await new Promise(res => setTimeout(res, 400));
        collectRows().forEach(r => { if (r.id) seen.set(r.id, r); });
        pos += step;
    }
    scroller.scrollTop = 0;
    return { rows: [...seen.values()] };
}"""
)

# Selects every row whose data-id is in the provided array.
# Strategy A: Bryntum widget programmatic API (grid._instance.selectRecords).
# Strategy B (fallback): click .b-check-cell — Bryntum's CSS class for the
# selection-column cell.  querySelector returns the FIRST .b-check-cell in the
# row, which is the row-selection column; the Aspiration column also renders as
# .b-check-cell but appears later in the DOM so it is never matched first.
# Returns { selected: N, missing: [id, ...] }.
_SELECT_BY_IDS_JS = (
    "async (recordIds) => { "
    + _FIND_EL_FN
    + """
    const host = findEl(document, 'c-bryntum-widget-host');
    if (!host) return { error: 'no-host' };
    const sr = host.shadowRoot;
    const scroller = sr.querySelector('.b-grid-body-container');
    if (!scroller) return { error: 'no-scroller' };

    const toSelect = new Set(recordIds);

    // --- Strategy A: Bryntum widget programmatic API ---
    const gridEl = sr.querySelector('.b-gridbase');
    const grid = gridEl && (gridEl._instance || gridEl._widget || gridEl.widget);
    if (grid && grid.store && typeof grid.selectRecords === 'function') {
        const records = (grid.store.records || []).filter(r => toSelect.has(String(r.id)));
        grid.selectRecords(records);
        await new Promise(r => setTimeout(r, 300));
        const selectedIds = new Set((grid.selectedRecords || []).map(r => String(r.id)));
        return {
            selected: selectedIds.size,
            missing: recordIds.filter(id => !selectedIds.has(id))
        };
    }

    // --- Strategy B: DOM click on .b-check-cell (row-selection column) ---
    const selected = new Set();

    function clickVisible() {
        for (const row of sr.querySelectorAll('.b-grid-row[data-id]')) {
            const id = row.dataset.id;
            if (!toSelect.has(id) || selected.has(id)) continue;
            // First .b-check-cell in the row is always the selection column
            const cell = row.querySelector('.b-check-cell') ||
                         row.querySelectorAll('.b-grid-cell')[0];
            if (cell) {
                const inner = cell.querySelector('input[type=checkbox]') ||
                              cell.querySelector('.b-checkbox');
                (inner || cell).click();
                selected.add(id);
            }
        }
    }

    clickVisible();
    const step = Math.max(scroller.clientHeight, 100);
    let pos = step;
    while (pos <= scroller.scrollHeight + step && selected.size < toSelect.size) {
        scroller.scrollTop = pos;
        await new Promise(res => setTimeout(res, 300));
        clickVisible();
        pos += step;
    }
    scroller.scrollTop = 0;
    return {
        selected: selected.size,
        missing: recordIds.filter(id => !selected.has(id))
    };
}"""
)

# Clears the current selection.  Same two-strategy pattern as _SELECT_BY_IDS_JS.
_CLEAR_SELECTION_JS = (
    "() => { "
    + _FIND_EL_FN
    + """
    const host = findEl(document, 'c-bryntum-widget-host');
    if (!host) return;
    const sr = host.shadowRoot;

    // Strategy A: Bryntum widget API
    const gridEl = sr.querySelector('.b-gridbase');
    const grid = gridEl && (gridEl._instance || gridEl._widget || gridEl.widget);
    if (grid && typeof grid.deselectAll === 'function') {
        grid.deselectAll();
        return;
    }

    // Strategy B: click .b-check-cell on each selected row to deselect
    for (const row of sr.querySelectorAll('.b-grid-row.b-selected, .b-grid-row[aria-selected="true"]')) {
        const cell = row.querySelector('.b-check-cell') ||
                     row.querySelectorAll('.b-grid-cell')[0];
        if (cell) {
            const inner = cell.querySelector('input[type=checkbox]') ||
                          cell.querySelector('.b-checkbox');
            (inner || cell).click();
        }
    }
}"""
)


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def load_csv(path=None):
    """
    Read the Manager Tracker CSV and split rows into approvals and rejections.

    Returns:
        tuple[list[dict], list[dict]]: (approvals, rejections)
    """
    csv_path = path or CSV_PATH
    approvals = []
    rejections = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            action = row.get("Final Action", "").strip()
            employee = row.get("Employee", "").strip()
            skill = row.get("Skill or Certification", "").strip()
            notes = row.get("Discussion Notes", "").strip()
            record_id = row.get("Record ID", "").strip()
            if action == "Approve":
                approvals.append(
                    {"employee": employee, "skill": skill, "record_id": record_id}
                )
            elif action == "Reject":
                rejections.append(
                    {
                        "employee": employee,
                        "skill": skill,
                        "record_id": record_id,
                        "notes": notes[:MAX_COMMENT_CHARS],
                    }
                )
    return approvals, rejections


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def wait_for_grid(page):
    """Wait until the Bryntum grid host appears anywhere in the shadow tree."""
    page.wait_for_function(_WAIT_FOR_GRID_JS, timeout=60_000)
    page.wait_for_timeout(2_000)


def get_all_rows(page):
    """
    Return all grid rows as a list of dicts keyed by column ID.
    Scrolls through virtual rows to collect all records.
    """
    result = page.evaluate(_GET_ALL_ROWS_JS)
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(f"get_all_rows failed: {result['error']}")
    return result.get("rows", [])


def select_rows_by_ids(page, record_ids):
    """
    Select grid rows matching the given record IDs.
    Returns dict: {selected: int, missing: list[str]}.
    """
    result = page.evaluate(_SELECT_BY_IDS_JS, list(record_ids))
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(f"select_rows_by_ids failed: {result['error']}")
    return result


def clear_selection(page):
    """Deselect all currently selected rows."""
    page.evaluate(_CLEAR_SELECTION_JS)


def match_row_id(rows, employee, skill):
    """Return the record ID for an employee+skill row, or None if not found."""
    for row in rows:
        if (row.get(_COL_EMPLOYEE, "").strip() == employee
                and row.get(_COL_SKILL, "").strip() == skill):
            return row.get("id")
    return None


# ---------------------------------------------------------------------------
# Button / modal helpers
# ---------------------------------------------------------------------------

def click_page_button(page, label):
    """Click a top-level Approve or Reject button on the page."""
    btn = page.get_by_role("button", name=label).first
    btn.wait_for(state="visible", timeout=15_000)
    btn.click()


def fill_and_confirm_modal(page, comment, confirm_label):
    """Fill the Comments textarea in the open modal and click the confirm button.

    We skip waiting for [role='dialog'] because Salesforce always has a hidden Aura
    error dialog in the DOM with that role (id="auraError", class="auraErrorBox") —
    Playwright's .first would resolve to that hidden element and time out.

    Instead we wait directly for the textarea, which only exists in the DOM when the
    approval/rejection modal is genuinely open.

    Textarea: matched by class slds-textarea (stable; id is dynamic).
    Confirm button: matched by title attribute (stable and unique):
        "Approve Skill or Certification Rating" / "Reject Skill or Certification Rating"
    Modal-closed signal: textarea transitions to hidden state.
    """
    # Capture the page immediately after the button click — shows whether the
    # modal actually opened (this is the first thing to check when debugging)
    screenshot(page, f"{confirm_label.lower()}_01_after_btn_click")

    # Wait for textarea — only present when the correct modal is open
    textarea = page.locator("textarea.slds-textarea")
    try:
        textarea.wait_for(state="visible", timeout=15_000)
    except PWTimeout:
        screenshot(page, f"{confirm_label.lower()}_ERROR_textarea_not_visible")
        raise
    textarea.fill(comment)

    # title is stable and unique; avoids colliding with same-text header buttons
    title = f"{confirm_label} Skill or Certification Rating"
    confirm_btn = page.locator(f"button[title='{title}']")
    try:
        confirm_btn.wait_for(state="visible", timeout=10_000)
    except PWTimeout:
        screenshot(page, f"{confirm_label.lower()}_ERROR_confirm_btn_not_visible")
        raise
    confirm_btn.click()

    # Textarea disappearing is a reliable signal the modal closed
    try:
        textarea.wait_for(state="hidden", timeout=30_000)
    except PWTimeout:
        screenshot(page, f"{confirm_label.lower()}_ERROR_modal_not_closing")
        raise
    page.wait_for_timeout(1_500)


def take_debug_screenshot(page, tag):
    """Save a screenshot for debugging failures."""
    path = SCREENSHOTS_DIR / f"debug_{tag}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  [debug] Screenshot saved: {path}")


def screenshot(page, step):
    """Save a timestamped workflow-step screenshot for the current run."""
    path = SCREENSHOTS_DIR / f"debug_{_RUN_TS}_{step}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  [screenshot] {path.name}")


# ---------------------------------------------------------------------------
# Pass orchestration
# ---------------------------------------------------------------------------

def execute_approval_pass(page, approvals):
    """
    Select all approval rows by record ID and submit the Approve action.

    Returns:
        dict: {"attempted": int, "succeeded": int, "missing": list[str]}
    """
    if not approvals:
        return {"attempted": 0, "succeeded": 0, "missing": []}

    approval_ids = [a["record_id"] for a in approvals if a["record_id"]]
    result = select_rows_by_ids(page, approval_ids)

    selected = result.get("selected", 0)
    missing = result.get("missing", [])

    print(f"  Selected {selected}/{len(approval_ids)} rows. Missing: {len(missing)}")
    if missing:
        print(f"  Missing IDs: {missing[:5]}{'...' if len(missing) > 5 else ''}")

    if selected > 0:
        screenshot(page, f"approval_01_{selected}_rows_selected")
        click_page_button(page, "Approve")
        fill_and_confirm_modal(page, APPROVE_COMMENT, "Approve")
        screenshot(page, "approval_02_after_confirm")

    return {
        "attempted": len(approval_ids),
        "succeeded": selected,
        "missing": missing,
    }


def execute_rejection_pass(page, rejections, all_rows):
    """
    Reject each row individually using Discussion Notes as the comment.
    all_rows is used to resolve employee+skill to a record ID for rows
    where the CSV record ID may not match (fallback by name).

    Returns:
        list[dict]: one entry per rejection with employee, skill, status, error.
    """
    results = []

    for idx, item in enumerate(rejections, start=1):
        emp = item["employee"]
        skill = item["skill"]
        notes = item["notes"]
        record_id = item["record_id"]
        entry = {"employee": emp, "skill": skill, "status": "unknown", "error": ""}

        # Try to resolve ID: use CSV ID first, fall back to name-match from live rows
        if not record_id:
            record_id = match_row_id(all_rows, emp, skill)

        if not record_id:
            entry["status"] = "skipped"
            entry["error"] = "Record ID not found in CSV or live grid rows"
            results.append(entry)
            continue

        print(f"\n  Rejecting: {emp} | {skill} ({record_id})")

        clear_selection(page)
        page.wait_for_timeout(300)

        sel_result = select_rows_by_ids(page, [record_id])
        if sel_result.get("selected", 0) == 0:
            entry["status"] = "skipped"
            entry["error"] = f"Row {record_id} not found on page — may have been already actioned"
            results.append(entry)
            continue

        screenshot(page, f"reject_{idx:02d}_01_selected")

        try:
            click_page_button(page, "Reject")
            fill_and_confirm_modal(page, notes, "Reject")
            entry["status"] = "success"
            screenshot(page, f"reject_{idx:02d}_02_done")
            print(f"    Rejected OK.")
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)
            take_debug_screenshot(page, f"reject_fail_{record_id}")
            print(f"    ERROR: {exc}")

        results.append(entry)
        page.wait_for_timeout(1_000)

    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run():
    approvals, rejections = load_csv()
    print(f"Loaded {len(approvals)} approvals and {len(rejections)} rejections from CSV.")

    shutil.rmtree(SCREENSHOTS_DIR, ignore_errors=True)
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    print(f"Screenshots will be saved to: {SCREENSHOTS_DIR}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        print(f"\n[1/4] Opening Mass Approve page: {MASS_APPROVE_URL}")
        page.goto(MASS_APPROVE_URL, wait_until="domcontentloaded")

        print(
            "\n>>> Log in via the browser window that just opened.\n"
            ">>> After the Mass Approve page loads and the grid is visible,\n"
            ">>> press ENTER here to continue."
        )
        input()

        print(">>> Waiting for the Bryntum grid to load…")
        try:
            wait_for_grid(page)
        except PWTimeout:
            take_debug_screenshot(page, "grid_timeout")
            print("WARNING: Grid did not appear in 60 s. Check debug screenshot.")
            input("Press ENTER when the grid is fully visible to retry…")
            wait_for_grid(page)

        print(">>> Collecting all rows from the grid…")
        all_rows = get_all_rows(page)
        print(f"    Found {len(all_rows)} rows.")

        if not all_rows:
            take_debug_screenshot(page, "no_rows")
            print("ERROR: No rows found — check debug screenshot and verify the page loaded.")
            browser.close()
            return

        screenshot(page, f"run_01_grid_loaded_{len(all_rows)}_rows")

        # ── Pass 1: Approvals ─────────────────────────────────────────────
        print(f"\n[3/4] Pass 1 — Approving {len(approvals)} records en masse…")
        approval_result = execute_approval_pass(page, approvals)
        print(
            f"  Submitted: {approval_result['succeeded']} approved, "
            f"{len(approval_result['missing'])} not found on page."
        )

        # Re-collect rows after approvals are removed from the queue
        print(">>> Re-collecting rows after approval pass…")
        page.wait_for_timeout(2_000)
        try:
            wait_for_grid(page)
            all_rows = get_all_rows(page)
            print(f"    {len(all_rows)} rows remaining.")
            screenshot(page, f"run_02_after_approval_{len(all_rows)}_rows_remain")
        except PWTimeout:
            print("WARNING: Grid not visible after approval — proceeding with original row data.")

        # ── Pass 2: Rejections ────────────────────────────────────────────
        print(f"\n[4/4] Pass 2 — Rejecting {len(rejections)} records individually…")
        rejection_results = execute_rejection_pass(page, rejections, all_rows)

        # ── Write results ─────────────────────────────────────────────────
        results = {
            "approvals": approval_result,
            "rejections": rejection_results,
        }
        with open(RESULTS_PATH, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n✓ Done. Results written to {RESULTS_PATH}")
        summary = {}
        for r in rejection_results:
            summary[r["status"]] = summary.get(r["status"], 0) + 1
        print(f"  Rejections: {summary}")

        input("\nPress ENTER to close the browser…")
        browser.close()


if __name__ == "__main__":
    run()
