---
description: Step 4 — Generate the review XLSX workbook and upload to Google Drive.
---

# Generate review artifacts (Step 4)

Run `python3 generate_review_artifacts.py` from the repo directory.

**What happens:** Auto-discovers the latest `skill_validation_detail_<ts>.csv`, builds `skill_rating_review.xlsx` with Overview, Manager Tracker, and per-employee tabs (with flags, cert evidence, dropdowns, and conditional formatting), then uploads to Google Drive.

**No arguments required.**

## After running

Check stdout for:
- `Saved: skill_rating_review.xlsx`
- `Google Drive upload complete.` OR `Opening Google Drive in Chrome for manual upload.`

Check the file exists:
```bash
ls -lh skill_rating_review.xlsx
```

## Success

- `skill_rating_review.xlsx` exists and is non-zero size
- Either uploaded to Drive silently OR browser opened to Drive for manual upload

## Failure

| Error | Fix |
|-------|-----|
| `No skill_validation_detail_*.csv found. Run validate_skill_ratings.py first.` | Re-run Step 3 first |
| `openpyxl not found` | `pip3 install openpyxl` |
| OAuth failure | Falls back automatically to opening Drive manually — not an error |

## Manager Tracker tab layout

The key output columns the user will fill:
- **Column L — Discussion Notes:** Free-text coaching or rejection rationale
- **Column N — Agreed Rating:** Final agreed rating (dropdown)
- **Column O — Final Action:** `Approve` / `Reject` / `Change To — See Notes` / `Pending Discussion`

## Manual gate after this step

**Do NOT proceed to `/mass-approve` until these are done:**

1. Open `skill_rating_review.xlsx` in Google Drive / Sheets
2. Fill **Discussion Notes** (column L) for every flagged row that will be Rejected
3. Set **Final Action** (column O) for every row — all must be either `Approve` or `Reject` (no Pending)
4. Run 1:1 conversations for any Discuss rows
5. Export Manager Tracker tab: **File → Download → Comma-separated values (.csv)**
6. Save the downloaded file to `~/Downloads/skill_rating_review.xlsx - Manager Tracker.csv` (that exact filename — the script hardcodes this path)

## Report back

Tell the user:
- Number of rows in Manager Tracker tab
- Number of per-employee tabs created
- Drive upload status
- Remind them of the manual gate steps before `/mass-approve`
