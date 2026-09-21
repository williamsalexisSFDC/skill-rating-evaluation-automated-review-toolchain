---
description: Step 5 — Execute approval and rejection passes in org62 from the completed Manager Tracker CSV.
---

# Mass approve and reject (Step 5)

Run `python3 mass_approve_skills.py` from the repo directory.

**What happens:** Reads `~/Downloads/skill_rating_review.xlsx - Manager Tracker.csv`, navigates to the org62 Mass Approve page, selects all `Final Action == Approve` rows by record ID in the Bryntum grid, clicks Approve with the standard comment, then individually selects and rejects each `Final Action == Reject` row using its Discussion Notes as the comment (max 4000 chars).

**No arguments required.**

## Pre-flight check

Before running, verify:
```bash
ls ~/Downloads/skill_rating_review.xlsx\ -\ Manager\ Tracker.csv
```
If it doesn't exist, stop — the user needs to export it from Google Sheets first (see `/generate-review` manual gate).

Also verify the file has the required columns:
- `Record ID`, `Employee`, `Skill or Certification`, `Discussion Notes`, `Final Action`
- `Final Action` values must be `Approve` or `Reject` (not `Pending Discussion`)

## After running

Read `mass_approve_results.json`:
```bash
python3 -c "import json; d=json.load(open('mass_approve_results.json')); print(json.dumps(d, indent=2))"
```

Check `screenshots/` for any error screenshots:
```bash
ls screenshots/ | grep -i error
ls screenshots/ | grep -i fail
```

## Success

- `mass_approve_results.json` has:
  - `approvals.succeeded == approvals.attempted`
  - `approvals.missing` is empty (`[]`)
  - All `rejections[].status == "success"`
- No `*ERROR*` or `*fail*` files in `screenshots/`

## Failure

| Error | Cause | Fix |
|-------|-------|-----|
| `FileNotFoundError` on CSV path | CSV not exported yet or saved with wrong name | Verify exact filename: `skill_rating_review.xlsx - Manager Tracker.csv` in `~/Downloads/` |
| Screenshot `*ERROR_textarea_not_visible*` | Modal never opened | The Approve/Reject button click may have been intercepted — check `*after_btn_click*` screenshot |
| Screenshot `*ERROR_modal_not_closing*` | Confirm button clicked but modal stuck | May be a Salesforce error; check for validation errors in the modal |
| Screenshot `*fallback_keyboard*` | CSS locator timed out — keyboard fallback used | Usually fine; confirm modal closed by checking `*ERROR_modal_not_closing*` is absent |
| `rejections[].status == "skipped"` | Record ID not found on page | Record may have already been approved/rejected in a previous run |
| `rejections[].status == "failed"` | Exception during reject flow | Check `rejections[].error` field and screenshots for that record |
| `approvals.missing` non-empty | Record IDs in CSV not found in grid | Records may already be approved or filtered from view |

## Report back

After reading `mass_approve_results.json`, report:
- **Approvals:** X attempted, Y succeeded, Z missing (list missing record IDs if any)
- **Rejections:** X success, Y skipped, Z failed
- For any failures: employee name, skill, error message
- For any error screenshots: which step failed, what the screenshot name indicates
- Overall: whether the run is complete or needs manual follow-up for any records
