#!/usr/bin/env bash
# Fast-forwards dev to main when dev is behind and has no local commits.
# No-ops when dev is ahead or already up to date.
# Requires: git remote `origin` with a `main` branch, GH_TOKEN in env.
set -euo pipefail

git fetch origin main

BEHIND=$(git rev-list --count HEAD..origin/main)
AHEAD=$(git rev-list --count origin/main..HEAD)

if [ "$BEHIND" -gt 0 ] && [ "$AHEAD" -eq 0 ]; then
    echo "dev is $BEHIND commit(s) behind main, 0 ahead -- fast-forwarding"
    git merge origin/main --ff-only
    git push origin HEAD:dev
elif [ "$BEHIND" -gt 0 ]; then
    echo "dev is $BEHIND behind and $AHEAD ahead of main -- diverged, PR will merge both"
else
    echo "dev is up to date with main"
fi
