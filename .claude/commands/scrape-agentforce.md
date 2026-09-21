---
description: Step 2 — Scrape Agentforce Resource Request evidence for each direct report from org62.
---

# Scrape Agentforce resource requests (Step 2)

Run `python3 scrape_agentforce_resource_requests.py` from the repo directory.

**What happens:** A Chromium window opens. After Okta SSO login, the script navigates each direct report's PSA Resource Request related list. Pass 1 collects RR metadata from list views; Pass 2 visits individual post-GA records with active statuses to retrieve the Primary Skill field. RRs are then classified against the Agentforce delivery-evidence criteria.

## Arguments

```bash
# Default: hardcoded My_Team41 contact list (current team)
python3 scrape_agentforce_resource_requests.py

# Generic: any manager's direct reports
python3 scrape_agentforce_resource_requests.py --manager-id 005Ded...

# Also write team_roster.csv from discovered roster
python3 scrape_agentforce_resource_requests.py --manager-id 005Ded... --roster-out team_roster.csv
```

## After running

Check stdout for:
- `Saved N rows → agentforce_resource_requests.csv`
- The `── Agentforce Delivery Evidence Summary ──` table

Check the file exists:
```
wc -l agentforce_resource_requests.csv
```

## Success

- Stdout shows row count and the evidence summary table
- `agentforce_resource_requests.csv` exists and is non-empty
- Columns: `Employee`, `RR Name`, `Primary Skill`, `Status`, `Start Date`, `End Date`, `Duration Days`, `AF Skill`, `Post GA`, `Active Status`, `Long Enough`, `Qualifying`
- Per-employee evidence level shown: `4-Specialist eligible`, `3-Advanced eligible`, or `Insufficient (N)`

## Failure

| Error | Cause | Fix |
|-------|-------|-----|
| `No contacts found` | Contact list selector changed or user not on correct page | Check `debug_contact_list.png` in repo dir |
| `No direct reports discovered` | Manager ID wrong or user has no reports in org | Verify Salesforce User ID starts with `005` |
| `Timed out waiting for manager's User page` | Slow page load | Re-run |
| CSV absent | Script error before save | Check full traceback |

If `debug_contact_list.png` or `debug_direct_reports.png` appear, share what they show.

## Report back

Tell the user:
- Total RR rows exported
- Per-employee evidence level (copy the summary table)
- Confirm they can proceed to Step 3 (`/validate-ratings`)
