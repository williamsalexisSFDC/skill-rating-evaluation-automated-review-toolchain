---
description: Request any change to the toolchain scripts — implements it, updates tests + README, commits, waits for the PR to merge, and reports a summary.
---

# Update the toolchain

You are the implementation agent for this toolchain. The user has described a change they want. Your job is to implement it completely — code, tests, README — get it merged to main, and report what changed.

## Step 1 — Clarify before touching any files

Restate the request in one sentence. Identify which of the five scripts is affected. If ambiguous, ask one question to resolve it. Do not start implementing until you understand exactly what the change is.

Example restatement: "You want `mass_approve_skills.py` to retry a failed rejection up to 3 times before marking it failed."

## Step 2 — Read the affected code

Read the relevant script(s) and the test file(s) that cover them. Do not rely on prior context — always read the current file state first.

Relevant test files:
- `tests/test_mass_approve.py` — covers `mass_approve_skills.py`
- Check for `tests/test_validate_skill_ratings.py`, `tests/test_generate_review_artifacts.py`, `tests/test_scrape_*.py` if those scripts are affected

## Step 3 — Implement the change

Edit the script(s). Follow the existing code style:
- No comments unless the WHY is non-obvious
- No error handling for scenarios that can't happen
- No extra abstractions or features beyond what was asked
- No backwards-compatibility shims

## Step 4 — Update or write tests

After every code change, update the affected test class(es). Rules:
- Coverage must stay at or above 90% (current: ~92%)
- Write tests that verify the new behavior, not just exercise lines
- If you removed a feature, remove or update the tests that covered it
- Mock `page.locator`, `page.evaluate`, `page.keyboard`, etc. at the boundary (don't test Playwright internals)
- Run tests locally to verify they pass before committing:
  ```bash
  python3 -m pytest tests/ --cov=validate_skill_ratings --cov=generate_review_artifacts --cov=mass_approve_skills --cov-fail-under=90 -q
  ```
  If they fail, fix before continuing.

## Step 5 — Update README.md

Update only the sections of `README.md` that are affected by the change. Do not rewrite the whole document.

Sections that typically need updating:
- The script's description under **Toolchain Components**
- **Button and modal selectors** (for `mass_approve_skills.py` UI changes)
- **Outputs** (if new files or changed file formats)
- The **Last updated** line at the top: format `YYYY-MM-DD — Iteration N: <one-line description>`

Read the current README to find the right iteration number before updating.

## Step 6 — Commit

Stage only the changed files (scripts, tests, README — not CSVs, screenshots, .coverage, or xlsx files):
```bash
git add <specific files>
git status  # verify only intended files are staged
git commit -m "<imperative summary>

<one or two sentences on why the change was made if non-obvious>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

## Step 7 — Push and wait for CI

Push to `origin/dev` (CI triggers on this branch):
```bash
git push origin dev-rebase:dev
```

Poll until the run completes:
```bash
gh run list --branch dev --limit 1
gh run watch <run-id> --exit-status
```

CI does three things on success:
1. Tests pass with ≥90% coverage
2. Auto-creates PR `dev → main`
3. Auto-merges the PR

If tests fail: read the failure output, fix the issue in the working tree, re-run tests locally, commit a new fix commit (do NOT amend), push again.

## Step 8 — Confirm merge

```bash
gh pr list --base main --state all --limit 3
```

Wait until the PR status shows `MERGED`. If the PR is open but not merging, check if auto-merge was enabled:
```bash
gh pr view <number> --json autoMergeRequest
```

## Step 9 — Report the aggregate summary

Report back with:

```
## Change summary

**Request:** <one-sentence restatement>

**Files changed:**
- `<script>`: <what changed>
- `tests/<test_file>`: <what changed in tests>
- `README.md`: <which section updated>

**Tests:** <N> total, <N> passing, <coverage>% coverage
**PR:** #<number> merged to main
**CI:** passed in <N>s
```

Do not report the task as complete until the PR shows MERGED.
