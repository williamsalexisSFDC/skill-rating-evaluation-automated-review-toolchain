---
description: Step 1 — Scrape skill/cert rating records from org62 Mass Approve page to CSV.
---

# Scrape skill ratings (Step 1)

Run `python3 scrape_skill_ratings.py` from the repo directory.

**What happens:** A Chromium window opens and navigates to the org62 Mass Approve Skills and Certification page. The user logs in via Okta SSO. The script scrolls the Bryntum shadow-DOM grid to load all rows, extracts every pending rating record, and writes them to CSV.

**No arguments required.**

## After running

Check stdout for:
- `Collected N records.`
- `Saved: skill_certification_ratings_<YYYYMMDD_HHMMSS>.csv`
- `Done. N records exported to: <path>`

Check the file exists and is non-empty:
```
wc -l skill_certification_ratings_*.csv
```

## Success

- Stdout shows "Collected N records" and "Done."
- CSV exists with N+1 lines (header + data rows)
- Columns: `Record ID`, `Rating ID`, `Resource`, `Skill or Certification`, `Evaluation Date`, `Notes`, `Rating`, `Aspiration`, `Approval Status`

## Failure

| Error | Cause | Fix |
|-------|-------|-----|
| `Timed out waiting for login or page load` | Page didn't load in time | Re-run; log in faster, ensure network is connected to org62 |
| `Bryntum host not found` | Grid shadow DOM host element not present | Refresh the page manually, confirm you're on the Mass Approve page, then re-run |
| `Scroll container not found` | Grid structure changed | Screenshot in repo dir — check it; may need selector update |
| Output CSV absent or 0 bytes | Script exited before saving | Check full traceback for the actual error |

## Report back

Tell the user:
- Row count scraped
- Output file path and timestamp
- Confirm they can proceed to Step 2 (`/scrape-agentforce`)
