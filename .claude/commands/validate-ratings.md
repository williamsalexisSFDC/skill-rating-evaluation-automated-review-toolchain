---
description: Step 3 — Apply 9 validation rule sets to all pending skill rating records.
---

# Validate skill ratings (Step 3)

Run `python3 validate_skill_ratings.py` from the repo directory.

**What happens:** Auto-discovers the latest `skill_certification_ratings_<ts>.csv` and all other input files by mtime, applies 9 rule sets to every record, and writes timestamped output CSVs and a human-readable feedback file.

**No arguments required.**

## Required input files (must all exist in repo dir)

| File | Source |
|------|--------|
| `skill_certification_ratings_<ts>.csv` | Step 1 output |
| `agentforce_resource_requests.csv` | Step 2 output |
| `employee_certifications.csv` | Static — maintained in repo |
| `team_roster.csv` | Static — manually maintained |
| `All Skills and Certifications-*.csv` | Org62 PSA catalog export (manual) |
| `FY26 DevOps Leveling Guide (Working Copy) - Current DevOps .csv` | Static |
| `Agentforce Ready and Expert Skills Ratings - Agentforce Skills .csv` | Static |

## After running

Check for the three output files:
```bash
ls -lt skill_validation_detail_*.csv | head -1
ls -lt skill_validation_summary_*.csv | head -1
ls -lt skill_validation_feedback_*.txt | head -1
```

## Success

All three files created with the same timestamp. `skill_validation_detail_<ts>.csv` has one row per skill record with flag columns populated.

## Failure

| Error | Fix |
|-------|-----|
| `No skill_certification_ratings_*.csv found` | Re-run Step 1 first |
| `Missing required file: <name>` | Check which file is missing; verify its exact filename matches the expected glob pattern |
| Script exits without creating output | Full traceback will name the missing/malformed input |

## Rule sets applied

1. PSA catalog check — skill name not in current catalog
2. AF minimum — Agentforce skill below 3-Advanced
3. Tier 1 cert gate — 3+ on AF skill without Agentforce Specialist cert
4. Data 360 cert gate — 3+ on Data Cloud skill without Data Cloud Consultant cert
5. Tier 2 grade ceiling — professional competency skill exceeds grade ceiling (Grade 5–6 max 3-Adv, Grade 7+ max 4-Spec)
6. Tier 3 delivery evidence — delivery AF skill at 3+ without cert AND qualifying RRs (≥2 for 3-Adv, ≥4 for 4-Spec)
7. Grade floor — rating below DevOps Leveling Guide minimum for employee's grade
8. Justification-required — Observability, Config Mgmt, Containerization, Env/Sandbox at 3+ (flagged for manager review)
9. 4-Specialist corroboration — no cert on file for any 4-Specialist claim

## Report back

Tell the user:
- Total records validated
- Flag counts by type (read from `skill_validation_summary_<ts>.csv`)
- Per-employee disposition breakdown (how many Approve / Discuss / Change Required)
- Output file paths
- Confirm they can proceed to Step 4 (`/generate-review`)
