#!/usr/bin/env bash
# Creates a dev→main PR if dev is ahead of main and no open PR exists.
# No-ops if dev has no new commits or a PR already exists.
# Requires: gh CLI, GH_TOKEN, GITHUB_REPOSITORY in env.
set -euo pipefail

AHEAD=$(gh api "repos/${GITHUB_REPOSITORY}/compare/main...dev" --jq '.ahead_by')

if [ "$AHEAD" -eq 0 ]; then
    echo "dev has no commits ahead of main -- no PR needed"
    exit 0
fi

EXISTING=$(gh pr list --base main --head dev --state open --json number --jq 'length')

if [ "$EXISTING" -eq 0 ]; then
    {
        echo "Automated PR: all tests passed with >=90% coverage."
        echo ""
        echo "**Triggered by:** push to \`dev\`"
        echo "**Status:** tests passed, coverage gate met"
        echo ""
        echo "Generated with Claude Code"
    } > /tmp/pr_body.txt
    gh pr create \
        --base main \
        --head dev \
        --title "dev -> main: automated merge (tests passed)" \
        --body-file /tmp/pr_body.txt
else
    echo "PR already exists -- skipping create"
fi
