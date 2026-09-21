---
description: Walk through the full 5-step skill-rating review pipeline from scrape to mass-approve.
---

# Run the full skill-rating review workflow

You are guiding the user through the FY26 Skill Rating Evaluation pipeline.
Walk each step in order, run the script when ready, report results clearly, and stop at the manual gate before proceeding to the final step.

## Before starting

Ask: "Which step do you want to start from?" If they say "the beginning" or don't specify, start at Step 1.

If they are resuming (e.g., "I already scraped the ratings"), confirm which outputs already exist and skip to the appropriate step.

---

## Step 1 — Scrape skill ratings

**Script:** `python3 scrape_skill_ratings.py`
**What it does:** Opens org62 in Chromium, lets the user log in, scrolls the Bryntum grid, and exports all pending skill/cert rating records.
**Inputs needed:** None. A browser window will open — user logs in interactively.
**Expected output:** `skill_certification_ratings_<YYYYMMDD_HHMMSS>.csv` in the repo dir.

Run it. When it finishes, confirm:
- "Collected N records." appears in stdout
- "Saved: skill_certification_ratings_<ts>.csv" appears
- The output CSV exists and is non-empty (`wc -l`)

**If it fails:** Check for `Timed out waiting for login`, `Bryntum host not found`, or `Scroll container not found` in output. Most failures are timing — tell the user to re-run and wait for the page to fully load before the script times out.

Report: row count, file path, timestamp.

---

## Step 2 — Scrape Agentforce resource requests

**Script:** `python3 scrape_agentforce_resource_requests.py`
**What it does:** Navigates each direct report's PSA Resource Request related list and classifies qualifying Agentforce RRs.
**Inputs needed:** None for the default team. For a different manager, the user would pass `--manager-id <Salesforce User ID>`.
**Expected output:** `agentforce_resource_requests.csv` in the repo dir.

Run it. When it finishes, confirm:
- "Saved N rows → agentforce_resource_requests.csv" appears
- The "Agentforce Delivery Evidence Summary" table is printed
- The CSV exists and is non-empty

**If it fails:** Check for "No contacts found", "No direct reports discovered", or a browser timeout. If `debug_contact_list.png` or `debug_direct_reports.png` appeared in the repo dir, share what those show.

Report: row count, per-employee evidence summary (4-Specialist eligible / 3-Advanced eligible / Insufficient).

---

## Step 3 — Validate skill ratings

**Script:** `python3 validate_skill_ratings.py`
**What it does:** Applies 9 rule sets to all pending records (PSA catalog check, AF minimum, Tier-1 cert gate, Data-360 cert gate, Tier-2 grade ceiling, Tier-3 delivery evidence, grade floor, justification-required, 4-Specialist corroboration).
**Inputs consumed (auto-discovered by mtime):**
- `skill_certification_ratings_<ts>.csv` (from step 1)
- `agentforce_resource_requests.csv` (from step 2)
- `employee_certifications.csv`
- `team_roster.csv`
- `All Skills and Certifications-*.csv`
- `FY26 DevOps Leveling Guide (Working Copy) - Current DevOps .csv`
- `Agentforce Ready and Expert Skills Ratings - Agentforce Skills .csv`

Run it. When it finishes, confirm:
- `skill_validation_detail_<ts>.csv` was created and is non-empty
- `skill_validation_summary_<ts>.csv` was created
- `skill_validation_feedback_<ts>.txt` was created

**If it fails:** "No skill_certification_ratings_*.csv found" → re-run step 1 first. "Missing required file" → check the specific file name mentioned and verify it exists.

Report: total records, flag counts by type (PSA catalog failures, AF cert gate failures, Tier-2 ceiling flags, Tier-3 evidence gaps), per-employee summary.

---

## Step 4 — Generate review artifacts

**Script:** `python3 generate_review_artifacts.py`
**What it does:** Builds `skill_rating_review.xlsx` (Overview, Manager Tracker, and per-employee tabs) and uploads to Google Drive.
**Inputs consumed (auto-discovered by mtime):**
- `skill_validation_detail_<ts>.csv` (from step 3)
- `employee_certifications.csv`

Run it. When it finishes, confirm:
- "Saved: skill_rating_review.xlsx" appears in stdout
- Either "Google Drive upload complete." OR "Opening Google Drive in Chrome for manual upload."
- `skill_rating_review.xlsx` exists in the repo dir

**If it fails:** "No skill_validation_detail_*.csv found" → re-run step 3. "openpyxl not found" → `pip3 install openpyxl`.

Report: number of rows in Manager Tracker, number of per-employee tabs, Drive upload status, link to Drive file if available.

---

## Manual gate — Complete the review spreadsheet

**Do NOT proceed to step 5 until this gate is cleared.**

Tell the user:
1. Open `skill_rating_review.xlsx` in Google Drive (or Sheets if uploaded).
2. Work through each flagged row in the Manager Tracker tab.
3. Fill in **Discussion Notes** (column L) for any Reject or Change Required rows.
4. Set **Final Action** (column O) for every row: `Approve`, `Reject`, or leave `Pending Discussion`.
5. When complete: File → Download → Comma-separated values → save as `skill_rating_review.xlsx - Manager Tracker.csv` to `~/Downloads/`.

Ask: "Let me know when the Manager Tracker CSV is saved to ~/Downloads/ and you're ready for step 5."

Wait for confirmation before continuing.

---

## Step 5 — Mass approve and reject

**Script:** `python3 mass_approve_skills.py`
**What it does:** Reads `~/Downloads/skill_rating_review.xlsx - Manager Tracker.csv`, selects all Approve rows in the Bryntum grid, clicks Approve with the standard comment, then iterates rejections individually with Discussion Notes.
**Inputs needed:** The downloaded Manager Tracker CSV (above).

Run it. A browser window opens — user logs in to org62 and presses ENTER when the grid is loaded.

After it finishes, read `mass_approve_results.json` and report:
- Approvals: attempted vs succeeded, any missing record IDs
- Rejections: success/failed/skipped counts, any failures with employee+skill+error

Check `screenshots/` for any `*ERROR*` files — if present, report what step they represent.

**If the script errors:** Check for RuntimeError in the traceback (confirm button not found), PWTimeout (modal/grid not loading), or CSV file not found at the expected path.

---

## Final report

Summarize the full run:
- Records scraped, validated, approved, rejected
- Any failures or skips that need manual follow-up
- Location of results: `mass_approve_results.json`
