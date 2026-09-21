#!/usr/bin/env bash
# Installs this toolchain's Claude Code slash commands to ~/.claude/commands/
# so they are available in every Claude Code session on this machine.
#
# Usage:
#   chmod +x setup.sh && ./setup.sh
#
# Idempotent — safe to re-run after pulling new versions of the skill files.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/.claude/commands"
DEST_DIR="$HOME/.claude/commands"

if [ ! -d "$SOURCE_DIR" ]; then
  echo "Error: .claude/commands/ not found in $SCRIPT_DIR" >&2
  echo "Make sure you are running this from the repo root." >&2
  exit 1
fi

mkdir -p "$DEST_DIR"

count=0
for file in "$SOURCE_DIR"/*.md; do
  [ -f "$file" ] || continue
  name=$(basename "$file")
  cp "$file" "$DEST_DIR/$name"
  printf "  installed: /%s\n" "$(basename "$name" .md)"
  count=$((count + 1))
done

echo ""
echo "$count slash command(s) installed to $DEST_DIR"
echo "Start a new Claude Code session to use them."
