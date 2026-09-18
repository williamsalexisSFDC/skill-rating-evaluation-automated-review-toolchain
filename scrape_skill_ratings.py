#!/usr/bin/env python3
"""
Quarterly scraper for PSE Skill & Certification Ratings pending approval.
URL: https://org62.lightning.force.com/lightning/n/Mass_Approve_Skills_and_Certification

Usage:
    python3 scrape_skill_ratings.py

Steps:
    1. A browser window opens and navigates to Salesforce.
    2. Log in with SFDC Okta (or your normal SSO method).
    3. Once the Mass Approve page loads, the script scrapes all records automatically.
    4. A timestamped CSV is saved to the same directory as this script.

Requirements:
    pip install playwright
    playwright install chromium
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

TARGET_URL = "https://org62.lightning.force.com/lightning/n/Mass_Approve_Skills_and_Certification"
OUTPUT_DIR = Path(__file__).parent

COLUMN_MAP = {
    "col-name": "Rating ID",
    "col-pse__resource__r_name": "Resource",
    "col-pse__skill_certification__r_name": "Skill or Certification",
    "col-pse__evaluation_date__c": "Evaluation Date",
    "col-pse__notes__c": "Notes",
    "col-pse__rating__c": "Rating",
    "col-pse__aspiration__c": "Aspiration",
    "col-pse__approval_status__c": "Approval Status",
}

SCRAPE_JS = """
async () => {
    function findEl(root, selector) {
        const found = root.querySelector(selector);
        if (found) return found;
        for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot) {
                const r = findEl(el.shadowRoot, selector);
                if (r) return r;
            }
        }
        return null;
    }

    const host = findEl(document, 'c-bryntum-widget-host');
    if (!host) return { error: 'Bryntum host not found — page may not have loaded yet.' };

    const sr = host.shadowRoot;
    const scroller = sr.querySelector('.b-grid-body-container');
    if (!scroller) return { error: 'Scroll container not found.' };

    // Read the expected total from the status label
    const statusEl = document.querySelector
        ? null
        : null;

    function collectRows() {
        const rows = [...sr.querySelectorAll('.b-grid-row')];
        return rows.map(row => {
            const cells = [...row.querySelectorAll('.b-grid-cell')];
            const record = { id: row.dataset.id };
            for (const cell of cells) {
                const col = cell.dataset.columnId;
                if (col && col !== 'ma_selection-column') {
                    record[col] = cell.textContent?.trim() ?? '';
                }
            }
            return record;
        });
    }

    const allRecords = new Map();
    collectRows().forEach(r => { if (r.id) allRecords.set(r.id, r); });

    const totalHeight = scroller.scrollHeight;
    const step = scroller.clientHeight;
    let pos = step;

    while (pos <= totalHeight + step) {
        scroller.scrollTop = pos;
        await new Promise(resolve => setTimeout(resolve, 500));
        collectRows().forEach(r => { if (r.id) allRecords.set(r.id, r); });
        pos += step;
    }

    // Scroll back to top
    scroller.scrollTop = 0;

    return {
        total: allRecords.size,
        records: [...allRecords.values()]
    };
}
"""


def wait_for_page(page):
    """Wait for the user to authenticate and the Mass Approve page to fully load."""
    print("\nWaiting for you to log in...")
    print("→ Log in with SFDC Okta in the browser window that opened.\n")

    # Wait until URL matches the target (post-login redirect)
    page.wait_for_url(
        "**/lightning/n/Mass_Approve_Skills_and_Certification",
        timeout=300_000  # 5 minutes to log in
    )
    print("Login detected. Waiting for the grid to load...")

    # Wait for the Bryntum grid container to appear
    page.wait_for_function(
        """() => {
            function findEl(root, sel) {
                if (root.querySelector(sel)) return true;
                for (const el of root.querySelectorAll('*'))
                    if (el.shadowRoot && findEl(el.shadowRoot, sel)) return true;
                return false;
            }
            return findEl(document, 'c-bryntum-widget-host');
        }""",
        timeout=60_000
    )

    # Extra wait for rows to render
    page.wait_for_timeout(2000)
    print("Grid loaded.\n")


def scrape(page) -> list[dict]:
    print("Scraping records — scrolling through the grid...")
    result = page.evaluate(SCRAPE_JS)

    if "error" in result:
        raise RuntimeError(f"Scrape failed: {result['error']}")

    print(f"Collected {result['total']} records.")
    return result["records"]


def to_csv(records: list[dict], path: Path):
    fieldnames = ["Record ID"] + list(COLUMN_MAP.values())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            row = {"Record ID": r.get("id", "")}
            for raw_col, clean_col in COLUMN_MAP.items():
                row[clean_col] = r.get(raw_col, "")
            writer.writerow(row)
    print(f"Saved: {path}")


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = OUTPUT_DIR / f"skill_certification_ratings_{timestamp}.csv"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context()
        page = context.new_page()

        print(f"Opening: {TARGET_URL}")
        page.goto(TARGET_URL)

        try:
            wait_for_page(page)
            records = scrape(page)
            to_csv(records, output_path)
            print(f"\nDone. {len(records)} records exported to:\n  {output_path}")
        except PlaywrightTimeoutError:
            print("\nTimed out waiting for login or page load. Please try again.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
