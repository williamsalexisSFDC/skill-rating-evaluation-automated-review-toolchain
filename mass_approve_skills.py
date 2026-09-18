"""
Mass Approve/Reject Skill and Certification Ratings via Playwright
=================================================================
Reads the Manager Tracker CSV export, then drives the Salesforce
Mass Approve Skills and Certification page in org62.

Pass 1 – Approve all rows where Final Action == "Approve" (en masse,
         single comment).
Pass 2 – Reject rows where Final Action == "Reject" one at a time,
         using Discussion Notes as the reject comment (max 4000 chars).

Run:
    python3 mass_approve_skills.py

The script pauses at org62 login so you can authenticate, then runs
both passes automatically.  Results are written to:
    ~/Downloads/mass_approve_results.json
"""

import csv
import json
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

CSV_PATH = (
    Path.home()
    / "Downloads"
    / "skill_rating_review.xlsx - Manager Tracker.csv"
)
RESULTS_PATH = Path.home() / "Downloads" / "mass_approve_results.json"
MASS_APPROVE_URL = (
    "https://org62.lightning.force.com/lightning/n/Mass_Approve_Skills_and_Certification"
)
APPROVE_COMMENT = "Reviewed and approved by PL, Alexis Williams."
MAX_COMMENT_CHARS = 4000


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
# Page interaction helpers
# ---------------------------------------------------------------------------

def wait_for_table(page):
    """Wait until the ratings table has at least one data row."""
    page.wait_for_selector(
        "tr[data-row-key-value], lightning-datatable table tbody tr",
        timeout=60_000,
    )


def get_all_rows(page):
    """
    Return a list of dicts with keys: tr, employee, skill, row_key.

    Reads all <tr data-row-key-value> elements from the Lightning datatable.
    Column layout (0-indexed after the checkbox cell):
        0 – checkbox, 1 – Rating Id, 2 – Resource, 3 – Skill or Certification, …
    """
    rows = []
    for tr in page.query_selector_all("tr[data-row-key-value]"):
        try:
            cells = tr.query_selector_all("td, th")
            cell_texts = [c.inner_text().strip() for c in cells]
            if len(cell_texts) < 4:
                continue
            rows.append(
                {
                    "tr": tr,
                    "employee": cell_texts[2],
                    "skill": cell_texts[3],
                    "row_key": tr.get_attribute("data-row-key-value") or "",
                }
            )
        except Exception:
            continue
    return rows


def scroll_to_load_all(page):
    """Scroll the datatable container to trigger lazy-loading until stable."""
    for _ in range(20):
        prev_count = len(page.query_selector_all("tr[data-row-key-value]"))
        page.evaluate(
            """
            const tables = document.querySelectorAll(
                'lightning-datatable, .slds-scrollable_y, [class*="scroll"]'
            );
            tables.forEach(t => { t.scrollTop = t.scrollHeight; });
            window.scrollTo(0, document.body.scrollHeight);
            """
        )
        time.sleep(1)
        new_count = len(page.query_selector_all("tr[data-row-key-value]"))
        if new_count == prev_count:
            break


def find_row_checkbox(page, employee, skill):
    """Return the checkbox element for employee+skill, or None if not found."""
    for row in get_all_rows(page):
        if row["employee"].strip() == employee and row["skill"].strip() == skill:
            return row["tr"].query_selector(
                "input[type='checkbox'], lightning-primitive-cell-checkbox input"
            )
    return None


def click_button_in_header(page, label):
    """Click the first Approve or Reject button in the page header."""
    btn = page.locator(
        f"button:has-text('{label}'), lightning-button button:has-text('{label}')"
    ).first
    btn.wait_for(state="visible", timeout=15_000)
    btn.click()


def fill_dialog_comment_and_confirm(page, comment, confirm_button_label):
    """Fill the Comments textarea in the open modal and click the confirm button."""
    page.wait_for_selector(
        "section[role='dialog'], div[role='dialog']", timeout=15_000
    )
    textarea = page.locator("textarea[name='Comments'], textarea").first
    textarea.wait_for(state="visible", timeout=10_000)
    textarea.fill(comment)
    modal = page.locator("section[role='dialog'], div[role='dialog']").first
    modal.locator(f"button:has-text('{confirm_button_label}')").first.click()
    page.wait_for_selector(
        "section[role='dialog'], div[role='dialog']",
        state="hidden",
        timeout=30_000,
    )


# ---------------------------------------------------------------------------
# Pass orchestration (extracted for testability)
# ---------------------------------------------------------------------------

def execute_approval_pass(page, approvals):
    """
    Select all approval checkboxes and submit the Approve action en masse.

    Returns:
        dict: {"succeeded": int, "failed": list[dict]}
    """
    approval_set = {(a["employee"], a["skill"]) for a in approvals}
    selected_count = 0
    failed_to_find = []

    for emp, skill in approval_set:
        cb = find_row_checkbox(page, emp, skill)
        if cb:
            if not cb.is_checked():
                cb.click()
            selected_count += 1
        else:
            failed_to_find.append({"employee": emp, "skill": skill})

    if selected_count > 0:
        click_button_in_header(page, "Approve")
        fill_dialog_comment_and_confirm(page, APPROVE_COMMENT, "Approve")
        time.sleep(3)

    return {
        "succeeded": selected_count,
        "failed": failed_to_find,
    }


def execute_rejection_pass(page, rejections):
    """
    Process each rejection individually: select → Reject → fill comment → confirm.

    Returns:
        list[dict]: one entry per rejection with keys employee, skill, status, error.
    """
    scroll_to_load_all(page)
    results = []

    for item in rejections:
        emp = item["employee"]
        skill = item["skill"]
        notes = item["notes"]
        entry = {"employee": emp, "skill": skill, "status": "unknown", "error": ""}

        cb = find_row_checkbox(page, emp, skill)
        if not cb:
            entry["status"] = "skipped"
            entry["error"] = "Row not found on page after approval pass"
            results.append(entry)
            continue

        for other_cb in page.query_selector_all(
            "tr[data-row-key-value] input[type='checkbox']:checked"
        ):
            other_cb.click()
        time.sleep(0.3)

        if not cb.is_checked():
            cb.click()
        time.sleep(0.3)

        try:
            click_button_in_header(page, "Reject")
            fill_dialog_comment_and_confirm(page, notes, "Reject")
            entry["status"] = "success"
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)

        results.append(entry)
        time.sleep(2)

    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run():
    approvals, rejections = load_csv()
    print(f"Loaded {len(approvals)} approvals and {len(rejections)} rejections from CSV.")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=300)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        print("\n[1/4] Navigating to org62 login…")
        page.goto("https://org62.lightning.force.com/", wait_until="domcontentloaded")
        print(
            "\n>>> Please log in to org62 in the browser window that just opened.\n"
            ">>> After you are fully logged in, press ENTER to continue."
        )
        input()

        print("\n[2/4] Navigating to Mass Approve Skills and Certification…")
        page.goto(MASS_APPROVE_URL, wait_until="domcontentloaded")
        time.sleep(3)

        print(">>> Waiting for the ratings table to load…")
        try:
            wait_for_table(page)
        except PWTimeout:
            print("WARNING: Table did not appear within 60 s — check the page manually.")
            input("Press ENTER when the table is visible…")

        print(">>> Scrolling to load all rows…")
        scroll_to_load_all(page)
        all_rows = get_all_rows(page)
        print(f"    Found {len(all_rows)} rows on page.")

        print(f"\n[3/4] Pass 1 — Approving {len(approvals)} records…")
        approval_result = execute_approval_pass(page, approvals)
        print(
            f"  Succeeded: {approval_result['succeeded']}, "
            f"not found: {len(approval_result['failed'])}"
        )

        print(f"\n[4/4] Pass 2 — Rejecting {len(rejections)} records individually…")
        rejection_results = execute_rejection_pass(page, rejections)

        results = {
            "approvals": {
                "attempted": len(approvals),
                "succeeded": approval_result["succeeded"],
                "failed": approval_result["failed"],
            },
            "rejections": rejection_results,
        }

        with open(RESULTS_PATH, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n✓ Done. Results written to {RESULTS_PATH}")
        rejection_summary: dict[str, int] = {}
        for r in rejection_results:
            rejection_summary[r["status"]] = rejection_summary.get(r["status"], 0) + 1
        print(f"  Rejections: {rejection_summary}")

        input("\nPress ENTER to close the browser…")
        browser.close()


if __name__ == "__main__":
    run()
