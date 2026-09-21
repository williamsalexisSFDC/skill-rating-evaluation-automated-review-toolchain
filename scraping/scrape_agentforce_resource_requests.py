#!/usr/bin/env python3
"""
Scrape Agentforce-related Resource Requests from org62 for direct reports.

Two modes:
  Generic (--manager-id):  Crawl the org chart from any manager's User page to discover
                           direct reports dynamically, then scrape each report's RRs.
                           Also writes team_roster.csv with names, User IDs, and grades.
  Legacy (no args):        Use the hardcoded My_Team41 contact list view (Alexis's team).

Two-pass RR approach:
  Pass 1 — List view: extract RR URL, Status, Start Date for all RRs per contact.
  Pass 2 — Individual records: visit only post-cutoff qualifying RRs to get Primary Skill.

Qualifying criteria for an Agentforce delivery-evidence RR:
  - Primary Skill or Certification contains "agentforce" (case-insensitive)
  - Status: Assigned, Closed, or In Progress
  - Start date >= 2024-10-01  (post Agentforce GA)
  - Duration >= 90 days        (covers Phase 0 / new-logo pursuit engagements)
    Assigned records started before today minus 90 days qualify automatically.
    Closed records need an End Date >= Start Date + 90 days.

Evidence thresholds (used by validate_skill_ratings.py):
  - 3-Advanced:   cert + >= 2 qualifying RRs
  - 4-Specialist: cert + >= 4 qualifying RRs

Outputs:
  ~/Downloads/agentforce_resource_requests.csv
  ~/Downloads/team_roster.csv   (--manager-id mode only)

Usage:
    pip3 install playwright --break-system-packages && playwright install chromium
    # Generic — any manager:
    python3 scrape_agentforce_resource_requests.py --manager-id 005Ded...
    # Legacy — Alexis's hardcoded list view:
    python3 scrape_agentforce_resource_requests.py
"""

import argparse
import csv
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

try:
    from playwright.sync_api import TimeoutError as PwTimeout
    from playwright_session import org62_session  # noqa: E402
except ImportError:
    sys.exit(
        "playwright not found.\n"
        "Run: pip3 install playwright --break-system-packages && playwright install chromium"
    )

DOWNLOADS   = Path(__file__).parent
ORG62_BASE  = "https://org62.lightning.force.com"
MY_TEAM_URL = f"{ORG62_BASE}/lightning/o/Contact/list?filterName=My_Team41"

ROSTER_FIELDS = ["Employee", "User ID", "Contact URL", "Grade"]

CUTOFF_DATE       = date(2024, 10, 1)
MIN_DURATION_DAYS = 90

AGENTFORCE_TERMS = ["agentforce"]
ACTIVE_STATUSES  = {"assigned", "closed", "complete", "completed", "in progress"}
# For these statuses the person is still staffed — use today, not the scheduled End Date
ONGOING_STATUSES = {"assigned", "in progress"}

OUTPUT_FIELDS = [
    "Employee", "RR Name", "Primary Skill", "Status",
    "Start Date", "End Date", "Duration Days",
    "AF Skill", "Post GA", "Active Status", "Long Enough", "Qualifying",
]


# ── Helpers ──────────────────────────────────────────────────────────────────────────────

def _parse_date(s: str):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%B %d, %Y"):
        try:
            return datetime.strptime((s or "").strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _is_agentforce(skill: str) -> bool:
    return any(t in (skill or "").lower() for t in AGENTFORCE_TERMS)


def _classify(skill: str, status: str, start_str: str, end_str: str) -> dict:
    start        = _parse_date(start_str)
    end          = _parse_date(end_str)
    status_lower = status.strip().lower()

    # Assigned / In Progress means the person is still actively staffed.
    # The End Date on a PSE RR is the *scheduled* end — not the actual end.
    # Use today so an ongoing engagement never gets falsely excluded.
    effective_end = date.today() if status_lower in ONGOING_STATUSES else (end or date.today())

    af          = _is_agentforce(skill)
    post_ga     = bool(start and start >= CUTOFF_DATE)
    active      = status_lower in ACTIVE_STATUSES
    days        = int((effective_end - start).days) if start else 0
    long_enough = days >= MIN_DURATION_DAYS
    qualifying  = "Yes" if (af and post_ga and active and long_enough) else "No"
    return {
        "AF Skill":      "Yes" if af else "No",
        "Post GA":       "Yes" if post_ga else "No",
        "Active Status": "Yes" if active else "No",
        "Long Enough":   "Yes" if long_enough else "No",
        "Duration Days": str(days) if start else "",
        "Qualifying":    qualifying,
    }


# ── Org chart discovery (generic mode) ─────────────────────────────────────────────────

def discover_direct_reports(page, manager_user_id: str) -> list[dict]:
    """
    Navigate to the manager's User page and extract their direct reports.

    Uses the standard Salesforce child relationship DirectReports (every User record
    exposes its direct-report Users via the ManagerId field — child relationship name
    is DirectReports in every standard Salesforce org including org62).

    Returns list of dicts: {name, user_id, user_url}
    """
    reports_url = f"{ORG62_BASE}/lightning/r/User/{manager_user_id}/related/DirectReports/view"
    print(f"  Navigating to Direct Reports list: {reports_url}")
    page.goto(reports_url)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)

    reports = []
    seen: set[str] = set()

    try:
        row_headers = page.get_by_role("rowheader").all()
        for header in row_headers:
            try:
                link = header.locator("a").first
                href = link.get_attribute("href", timeout=500) or ""
                text = (link.inner_text(timeout=500) or "").strip()
                if not text or not href or href in seen:
                    continue
                seen.add(href)
                url      = href if href.startswith("http") else ORG62_BASE + href
                m        = re.search(r"/([A-Za-z0-9]{15,18})/view", url)
                user_id  = m.group(1) if m else ""
                reports.append({"name": text, "user_id": user_id, "user_url": url})
            except Exception:
                continue
    except Exception as e:
        print(f"  discover_direct_reports error: {e}")

    if not reports:
        shot = DOWNLOADS / "debug_direct_reports.png"
        page.screenshot(path=str(shot), full_page=True)
        print(f"  No direct reports found. URL: {page.url} | Debug screenshot → {shot.name}")

    return reports


def get_contact_url_for_user(page, user_id: str, user_name: str) -> str:
    """
    Find the PSA Contact record URL for a given Salesforce User ID.

    PSA stores a Salesforce User lookup (pse__Salesforce_User__c) on Contact, creating a
    child relationship pse__Resources__r on the User record.  Navigate to that related list
    and return the first Contact URL found.  Falls back to empty string on failure.
    """
    resources_url = (
        f"{ORG62_BASE}/lightning/r/User/{user_id}"
        "/related/pse__Resources__r/view"
    )
    page.goto(resources_url)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(1.5)

    try:
        row_headers = page.get_by_role("rowheader").all()
        for header in row_headers:
            try:
                link = header.locator("a").first
                href = link.get_attribute("href", timeout=500) or ""
                text = (link.inner_text(timeout=500) or "").strip()
                if text and href:
                    return href if href.startswith("http") else ORG62_BASE + href
            except Exception:
                continue
    except Exception:
        pass

    # Fallback: try generic Contacts related list
    contacts_url = (
        f"{ORG62_BASE}/lightning/r/User/{user_id}"
        "/related/Contacts/view"
    )
    page.goto(contacts_url)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(1.5)

    try:
        row_headers = page.get_by_role("rowheader").all()
        for header in row_headers:
            try:
                link = header.locator("a").first
                href = link.get_attribute("href", timeout=500) or ""
                text = (link.inner_text(timeout=500) or "").strip()
                if text and href:
                    return href if href.startswith("http") else ORG62_BASE + href
            except Exception:
                continue
    except Exception:
        pass

    print(f"  Could not find Contact for User {user_name} ({user_id})")
    shot = DOWNLOADS / f"debug_contact_lookup_{user_id}.png"
    page.screenshot(path=str(shot))
    return ""


def scrape_grade_from_user(page) -> str:
    """
    Best-effort extraction of job grade / level from the current User detail page.

    Looks for common Salesforce field label patterns (Grade, Job Level, Band, Level).
    Returns a string like "Grade 6" or "Grade 7", or "" if not found.
    """
    # Scan all list items (Lightning detail fields are rendered as role="listitem")
    try:
        items = page.get_by_role("listitem").all()
        for item in items:
            try:
                label = (item.inner_text(timeout=500) or "").strip()
                # Look for "Grade N" pattern inside the field block
                m = re.search(r"\bGrade\s+(\d+)\b", label, re.IGNORECASE)
                if m:
                    return f"Grade {m.group(1)}"
                # Also try Band / Level patterns common in Salesforce HR fields
                m2 = re.search(r"\b(?:Band|Level)\s+(\d+)\b", label, re.IGNORECASE)
                if m2:
                    return f"Grade {m2.group(1)}"
            except Exception:
                continue
    except Exception:
        pass

    # Last resort: grep the raw page text
    try:
        body = page.inner_text("body", timeout=3000)
        m = re.search(r"\bGrade\s+(\d+)\b", body, re.IGNORECASE)
        if m:
            return f"Grade {m.group(1)}"
    except Exception:
        pass

    return ""


def build_team_from_manager(page, manager_user_id: str) -> list[dict]:
    """
    Full org-chart traversal: discover direct reports, then for each report
    find their PSA Contact URL and scrape their grade.

    Returns list of dicts: {name, user_id, contact_url, grade}
    """
    direct_reports = discover_direct_reports(page, manager_user_id)
    if not direct_reports:
        return []

    print(f"\nFound {len(direct_reports)} direct reports:")
    for r in direct_reports:
        print(f"  {r['name']} ({r['user_id']})")

    team = []
    for report in direct_reports:
        print(f"\n  Resolving Contact for {report['name']}…")
        # Navigate to the User page to scrape grade before leaving it
        page.goto(report["user_url"])
        page.wait_for_load_state("domcontentloaded")
        time.sleep(1.5)
        grade = scrape_grade_from_user(page)

        contact_url = get_contact_url_for_user(page, report["user_id"], report["name"])
        team.append({
            "name":        report["name"],
            "user_id":     report["user_id"],
            "contact_url": contact_url,
            "grade":       grade,
        })
        print(f"    Grade: {grade or '(not found)'}  |  Contact: {contact_url or '(not found)'}")

    return team


def save_roster(team: list[dict], path: Path):
    """Write team_roster.csv for use by validate_skill_ratings.py."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ROSTER_FIELDS)
        w.writeheader()
        for member in team:
            w.writerow({
                "Employee":    member["name"],
                "User ID":     member["user_id"],
                "Contact URL": member["contact_url"],
                "Grade":       member["grade"],
            })
    print(f"Roster saved ({len(team)} members) → {path.name}")


# ── Contact discovery (legacy list-view mode) ────────────────────────────────────────────────

def get_contacts(page) -> list[dict]:
    """
    Extract team members from the My_Team41 list view.

    Lightning list views render name links inside rowheader cells using web components
    with shadow DOM. Playwright's role-based locators (get_by_role) pierce shadow DOM
    automatically; document.querySelectorAll does not.

    Contact record URLs in the list view use the form /lightning/r/{RecordId}/view
    (no object-type name in the path).  We extract the ID and later construct the
    explicit Contact related-list URL: /lightning/r/Contact/{ID}/related/...
    """
    time.sleep(2)  # let Lightning finish rendering rows

    contacts = []
    seen: set[str] = set()

    try:
        row_headers = page.get_by_role("rowheader").all()
        for header in row_headers:
            try:
                link = header.locator("a").first
                href = link.get_attribute("href", timeout=500) or ""
                text = (link.inner_text(timeout=500) or "").strip()
                if text and href and href not in seen:
                    url = href if href.startswith("http") else ORG62_BASE + href
                    contacts.append({"name": text, "url": url})
                    seen.add(href)
            except Exception:
                continue
    except Exception as e:
        print(f"  get_contacts error: {e}")

    if not contacts:
        shot = DOWNLOADS / "debug_contact_list.png"
        page.screenshot(path=str(shot), full_page=True)
        print(f"  No contacts found. Debug screenshot → {shot.name}")
        print(f"  URL: {page.url}  |  Title: {page.title()}")

    return contacts


# ── Pass 1: RR list extraction ───────────────────────────────────────────────────────────────

def _extract_rr_list_page(page) -> list[dict]:
    """
    Extract lightweight RR rows from a single list-view page.
    Returns dicts with rr_name, rr_url, role, status, start_date.
    Does NOT include Primary Skill — that requires individual record visits (Pass 2).
    """
    rows_data = []
    rows = page.get_by_role("row").all()

    for row in rows:
        try:
            # Only data rows have a rowheader with a link
            rr_link = row.get_by_role("rowheader").locator("a").first
            href = rr_link.get_attribute("href", timeout=300)
            if not href:
                continue
            rr_name = (rr_link.inner_text(timeout=300) or "").strip()
            rr_url  = href if href.startswith("http") else ORG62_BASE + href

            # Gridcells: [0] empty, [1] "Select Item N", [2] Role, [3] Status, [4] Start Date, [5] Action
            cells = row.get_by_role("gridcell").all()
            cell_texts = []
            for c in cells:
                try:
                    cell_texts.append(c.inner_text(timeout=300).strip())
                except Exception:
                    cell_texts.append("")
            role       = cell_texts[2] if len(cell_texts) > 2 else ""
            status     = cell_texts[3] if len(cell_texts) > 3 else ""
            start_date = cell_texts[4] if len(cell_texts) > 4 else ""

            rows_data.append({
                "rr_name":    rr_name,
                "rr_url":     rr_url,
                "role":       role,
                "status":     status,
                "start_date": start_date,
            })
        except Exception:
            continue

    return rows_data


def get_all_rr_list_rows(page) -> list[dict]:
    """Collect Pass-1 rows across all pages of the list view."""
    all_rows = []
    while True:
        all_rows.extend(_extract_rr_list_page(page))
        next_btn = page.locator("button[title='Next Page']:not([disabled])")
        if next_btn.count() > 0:
            next_btn.first.click()
            time.sleep(1.5)
        else:
            break
    return all_rows


def needs_pass2(row: dict) -> bool:
    """True if this RR warrants a Primary Skill lookup (post-cutoff, active status)."""
    start = _parse_date(row["start_date"])
    return (
        bool(start and start >= CUTOFF_DATE)
        and row["status"].strip().lower() in ACTIVE_STATUSES
    )


# ── Pass 2: Individual RR record ───────────────────────────────────────────────────────────────

def get_rr_primary_skill_and_end_date(page, rr_url: str) -> tuple[str, str]:
    """
    Navigate to an individual pse__Resource_Request__c record and return
    (primary_skill, end_date).  Both may be empty strings on failure.
    """
    page.goto(rr_url)
    page.wait_for_load_state("domcontentloaded")

    # Wait for the Details tab content to render — Lightning renders async after DOMContentLoaded
    try:
        page.wait_for_selector("text=Primary Skill or Certification", timeout=15_000)
    except Exception:
        pass

    primary_skill = ""
    end_date      = ""

    # Primary Skill or Certification — listitem with role="listitem" (Lightning Web Component,
    # not a native <li> tag — must use get_by_role, not locator("li"))
    try:
        skill_li  = page.get_by_role("listitem").filter(has_text="Primary Skill or Certification").first
        skill_lnk = skill_li.locator("a").first
        raw = (skill_lnk.inner_text(timeout=5000) or "").strip()
        primary_skill = raw.lstrip("*").strip()  # PSE prefixes primary skill with *
    except Exception:
        pass

    # End Date — also a role="listitem" field
    if not end_date:
        try:
            end_li  = page.get_by_role("listitem").filter(has_text="End Date").first
            end_txt = end_li.inner_text(timeout=3000)
            m = re.search(r"\d{1,2}/\d{1,2}/\d{4}", end_txt)
            if m:
                end_date = m.group(0)
        except Exception:
            pass

    return primary_skill, end_date


# ── Per-contact orchestration ───────────────────────────────────────────────────────────────────

def process_contact(page, contact: dict) -> list[dict]:
    print(f"  → {contact['name']}")

    # Extract the Salesforce record ID from the list-view URL
    # Format: /lightning/r/{RecordId}/view  (no object-type name)
    id_match = re.search(r"/lightning/r/([A-Za-z0-9]{15,18})/", contact["url"])
    if not id_match:
        print("     Could not parse Contact ID from URL — skipping")
        return []

    contact_id = id_match.group(1)

    # Navigate to the PSE Resource Requests related list
    # Note: the related-list URL DOES require the object-type name "Contact"
    rr_list_url = (
        f"{ORG62_BASE}/lightning/r/Contact/{contact_id}"
        "/related/pse__Resource_Requests__r/view"
    )
    page.goto(rr_list_url)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)

    if "page not found" in (page.title() or "").lower():
        print("     Resource Requests related list not found — skipping")
        return []

    # ── Pass 1: collect list-view rows ───────────────────────────────────────
    list_rows = get_all_rr_list_rows(page)
    print(f"     Pass 1: {len(list_rows)} total RRs in list")

    qualifying_candidates = [r for r in list_rows if needs_pass2(r)]
    print(f"     Pass 2 candidates (post-Oct 2024, active): {len(qualifying_candidates)}")

    # ── Pass 2: visit each candidate record to get Primary Skill ─────────────────
    result_rows = []
    for rr in qualifying_candidates:
        primary_skill, end_date = get_rr_primary_skill_and_end_date(page, rr["rr_url"])

        q = _classify(primary_skill, rr["status"], rr["start_date"], end_date)
        result_rows.append({
            "Employee":      contact["name"],
            "RR Name":       rr["rr_name"],
            "Primary Skill": primary_skill,
            "Status":        rr["status"],
            "Start Date":    rr["start_date"],
            "End Date":      end_date,
            **q,
        })

        af  = "AF" if q["AF Skill"] == "Yes" else "  "
        qfy = "QUALIFYING" if q["Qualifying"] == "Yes" else "-"
        print(f"       {rr['rr_name']:12}  {rr['start_date']:10}  {rr['status']:10}  "
              f"{af}  {qfy}  |  {primary_skill[:60]}")

    af_count = sum(1 for r in result_rows if r["AF Skill"] == "Yes")
    q_count  = sum(1 for r in result_rows if r["Qualifying"] == "Yes")
    print(f"     Results: {len(result_rows)} visited | {af_count} Agentforce | {q_count} qualifying")
    return result_rows


# ── Output ──────────────────────────────────────────────────────────────────────────────

def save(rows: list[dict], path: Path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nSaved {len(rows)} rows → {path.name}")


def print_summary(rows: list[dict]):
    by_emp: dict[str, dict] = {}
    for r in rows:
        e = r["Employee"]
        if e not in by_emp:
            by_emp[e] = {"total": 0, "af": 0, "q": 0}
        by_emp[e]["total"] += 1
        if r.get("AF Skill") == "Yes":
            by_emp[e]["af"] += 1
        if r.get("Qualifying") == "Yes":
            by_emp[e]["q"] += 1

    print("\n── Agentforce Delivery Evidence Summary ──")
    print(f"{'Employee':<25} {'RRs Checked':>12} {'AF RRs':>8} {'Qualifying':>12}  Evidence Level")
    print("─" * 76)
    for emp, d in sorted(by_emp.items()):
        q  = d["q"]
        ev = (
            "4-Specialist eligible" if q >= 4
            else "3-Advanced eligible" if q >= 2
            else f"Insufficient ({q})"
        )
        print(f"{emp:<25} {d['total']:>12} {d['af']:>8} {q:>12}  {ev}")

    print(
        "\nCriteria: post Oct 2024 ·90 days · Assigned/Closed/In Progress · "
        "Primary Skill contains 'agentforce'"
        "\nThresholds: 3-Advanced = cert + 2+ qualifying RRs  |  "
        "4-Specialist = cert + 4+ qualifying RRs"
    )


# ── Entry point ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Agentforce Resource Requests for a manager's direct reports."
    )
    parser.add_argument(
        "--manager-id",
        metavar="USER_ID",
        help=(
            "Salesforce User ID of the manager whose direct reports to crawl "
            "(e.g. 005Ded...).  When omitted, falls back to the legacy My_Team41 "
            "Contact list view."
        ),
    )
    parser.add_argument(
        "--roster-out",
        metavar="PATH",
        default=str(DOWNLOADS / "team_roster.csv"),
        help="Where to write team_roster.csv (default: ~/Downloads/team_roster.csv). "
             "Only written in --manager-id mode.",
    )
    args = parser.parse_args()

    all_rows: list[dict] = []

    with org62_session() as page:
        if args.manager_id:
            # ── Generic mode: org-chart traversal ──────────────────────────────────
            print(f"Generic mode — manager User ID: {args.manager_id}")
            print("Navigate to org62 and log in if prompted. Waiting for page load…\n")

            # Navigate to manager's User page first so the browser can handle login
            manager_url = f"{ORG62_BASE}/lightning/r/User/{args.manager_id}/view"
            page.goto(manager_url)
            try:
                # Wait until at least one list item (detail field) is visible — means the
                # page has rendered past the login screen
                page.get_by_role("listitem").first.wait_for(timeout=120_000)
            except PwTimeout:
                print("Timed out waiting for manager's User page. Check your login.")
                return

            team = build_team_from_manager(page, args.manager_id)
            if not team:
                print("No direct reports discovered — nothing to scrape.")
                return

            # Save roster so validate_skill_ratings.py can pick it up automatically
            save_roster(team, Path(args.roster_out))

            # Build contact list from team roster (same shape as legacy contacts list)
            contacts = [
                {"name": m["name"], "url": m["contact_url"]}
                for m in team
                if m["contact_url"]
            ]
            skipped = [m["name"] for m in team if not m["contact_url"]]
            if skipped:
                print(f"\nSkipping (no Contact found): {skipped}")

        else:
            # ── Legacy mode: hardcoded My_Team41 list view ────────────────────
            print("Legacy mode — navigating to My_Team41 contact list…")
            page.goto(MY_TEAM_URL)

            try:
                page.get_by_role("rowheader").first.wait_for(timeout=90_000)
            except PwTimeout:
                print("Waiting for login / page load…")
                page.get_by_role("rowheader").first.wait_for(timeout=120_000)

            time.sleep(1)
            contacts = get_contacts(page)

        if not contacts:
            print("No contacts found.")
            return

        print(f"\nProcessing {len(contacts)} contacts: {[c['name'] for c in contacts]}\n")

        for ct in contacts:
            rows = process_contact(page, ct)
            all_rows.extend(rows)
            print()

    out = DOWNLOADS / "agentforce_resource_requests.csv"
    save(all_rows, out)
    print_summary(all_rows)


if __name__ == "__main__":
    main()
