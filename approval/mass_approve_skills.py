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
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from bryntum_grid import (  # noqa: E402
    wait_for_grid,
    get_all_rows,
    select_rows_by_ids,
    clear_selection,
)

# Timestamp stamped on every screenshot filename for this process invocation
_RUN_TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

CSV_PATH = (
    Path.home()
    / "Downloads"
    / "skill_rating_review.xlsx - Manager Tracker.csv"
)
RESULTS_PATH = Path(__file__).parent.parent / "mass_approve_results.json"
SCREENSHOTS_DIR = Path(__file__).parent.parent / "screenshots"
MASS_APPROVE_URL = (
    "https://org62.lightning.force.com/lightning/n/Mass_Approve_Skills_and_Certification"
)
APPROVE_COMMENT = "Reviewed and approved by PL, Alexis Williams."
MAX_COMMENT_CHARS = 4000

# Column IDs used by the Bryntum grid on the Mass Approve page
_COL_EMPLOYEE = "col-pse__resource__r_name"
_COL_SKILL = "col-pse__skill_certification__r_name"


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
    """Click the Approve or Reject action button in the grid header.

    Uses lightning-button[data-id] rather than get_by_role(name=label) because
    Playwright's get_by_role does substring matching — 'Approve' would match the
    nav-bar tab management button for 'Mass Approve Skills...' before reaching
    the grid button, opening a tab dropdown instead of the approval modal.

    Presses Escape first to close any open dropdowns whose backdrop overlay
    would otherwise intercept the click.
    """
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    btn = page.locator(f"lightning-button[data-id='{label.lower()}'] button")
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
    Confirm button: the <button> lives inside lightning-button's shadow root.
        Strategy 1: compound CSS "lightning-button button[title='...']" — the same
        pattern that works for the page Approve/Reject buttons (Playwright pierces the
        lightning-button host's shadow root when the host is explicitly named).
        Strategy 2: keyboard Tab×2 + Enter from the textarea — bypasses all shadow
        DOM issues; Tab order in this modal is: textarea → Cancel → Approve.
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

    # Strategy 1: compound CSS anchored at the lightning-button host element.
    # Playwright can pierce a named shadow host; the page Approve/Reject buttons
    # are found the same way (lightning-button[data-id=...] button).
    title = f"{confirm_label} Skill or Certification Rating"
    confirm_btn = page.locator(f"lightning-button button[title='{title}']")
    try:
        confirm_btn.wait_for(state="visible", timeout=5_000)
        confirm_btn.click()
    except PWTimeout:
        # Strategy 2: keyboard nav — Tab from textarea skips to Cancel, second Tab
        # lands on Approve/Reject, Enter activates it.  Works regardless of shadow DOM.
        screenshot(page, f"{confirm_label.lower()}_fallback_keyboard")
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        page.keyboard.press("Enter")

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
