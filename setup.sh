#!/usr/bin/env bash
#
# @author Alexis Williams
# @description Turnkey setup for the FY26 Skill Rating Evaluation toolchain.
#              Installs all system, Python, and dev dependencies, then registers
#              the Claude Code slash commands to ~/.claude/commands/.
#
# Usage:
#   chmod +x setup.sh && ./setup.sh [--dev] [--verbose]
#
# Flags:
#   --dev       Also install dev dependencies (pytest, flake8, pre-commit, bats)
#   --verbose   Show full output from installers instead of suppressing it
#
# Idempotent — safe to re-run after pulling updates.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DEV=false
VERBOSE=false

for arg in "$@"; do
  case "$arg" in
    --dev)     INSTALL_DEV=true ;;
    --verbose) VERBOSE=true ;;
  esac
done

# ── Logging / helpers ─────────────────────────────────────────────────────────

log()     { echo "==> $*"; }
ok()      { echo "    ✓ $*"; }
warn()    { echo "    ⚠ $* (skipping)" >&2; }
fail()    { echo "✗  $*" >&2; exit 1; }
need()    { command -v "$1" >/dev/null 2>&1; }
is_mac()  { [[ "$(uname -s)" == "Darwin" ]]; }

run() {
  if [[ "$VERBOSE" == true ]]; then "$@"; else "$@" >/dev/null 2>&1; fi
}

# ── Homebrew ──────────────────────────────────────────────────────────────────

ensure_brew() {
  need brew && return 0
  is_mac || return 0   # non-macOS: brew not applicable, proceed

  log "Installing Homebrew…"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    >/dev/null 2>&1 || true

  # Apple Silicon and Intel paths
  [[ -d /opt/homebrew/bin ]] && export PATH="/opt/homebrew/bin:$PATH"
  [[ -d /usr/local/bin    ]] && export PATH="/usr/local/bin:$PATH"

  need brew || warn "Homebrew install failed — continuing without it"
}

# Install a CLI via brew (macOS) or print a hint for Linux
# Usage: ensure_cli <binary> <brew_pkg> [<apt_pkg>] [<hint>]
ensure_cli() {
  local bin="$1" brew_pkg="$2" apt_pkg="${3:-}" hint="${4:-}"
  need "$bin" && { ok "$bin"; return 0; }

  if is_mac && need brew; then
    log "Installing $bin via Homebrew…"
    run brew install "$brew_pkg" || run brew reinstall "$brew_pkg" || true
    need "$bin" && { ok "$bin"; return 0; }
  elif ! is_mac && [[ -n "$apt_pkg" ]] && need apt-get; then
    log "Installing $bin via apt…"
    run sudo apt-get install -y "$apt_pkg" || true
    need "$bin" && { ok "$bin"; return 0; }
  fi

  if [[ -n "$hint" ]]; then warn "$bin not found — $hint"; else warn "$bin not found"; fi
  return 1
}

# ── Python packages ───────────────────────────────────────────────────────────

pip_install() {
  local pkg="$1"
  run python3 -m pip install --quiet --upgrade "$pkg"
  ok "pip: $pkg"
}

pip_install_r() {
  local reqfile="$1"
  [[ -f "$reqfile" ]] || return 0
  run python3 -m pip install --quiet --upgrade -r "$reqfile"
  ok "pip: $(basename "$reqfile")"
}

# ── System dependencies ───────────────────────────────────────────────────────

log "Checking system dependencies…"

ensure_brew

# Python 3.11+
if need python3; then
  PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  ok "python3 ($PY_VER)"
else
  ensure_cli python3 python3 python3 "install Python 3 from https://python.org" || \
    fail "Python 3 is required."
fi

# Playwright requires Chromium — install it after pip install
ensure_cli git git git ""

# bats-core — only when --dev; used by CI shell script tests
if [[ "$INSTALL_DEV" == true ]]; then
  ensure_cli bats bats-core bats ""
fi

# actionlint — validates GitHub Actions workflow files
if [[ "$INSTALL_DEV" == true ]]; then
  if ! need actionlint; then
    if is_mac && need brew; then
      log "Installing actionlint via Homebrew…"
      run brew install actionlint && ok "actionlint"
    else
      log "Installing actionlint via download script…"
      TMP_DIR="$(mktemp -d)"
      bash <(curl -sL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash) \
        --install-dir "$TMP_DIR" >/dev/null 2>&1 || true
      if [[ -f "$TMP_DIR/actionlint" ]]; then
        sudo mv "$TMP_DIR/actionlint" /usr/local/bin/actionlint || \
          cp "$TMP_DIR/actionlint" "$HOME/.local/bin/actionlint" || true
      fi
      need actionlint && ok "actionlint" || warn "actionlint install failed"
      rm -rf "$TMP_DIR"
    fi
  else
    ok "actionlint"
  fi
fi

# ── Python packages ───────────────────────────────────────────────────────────

log "Installing Python dependencies…"

pip_install_r "$SCRIPT_DIR/requirements.txt"

if [[ "$INSTALL_DEV" == true ]]; then
  pip_install_r "$SCRIPT_DIR/requirements-dev.txt"
fi

# ── Playwright browser ────────────────────────────────────────────────────────

log "Installing Playwright Chromium browser…"
if run python3 -m playwright install chromium; then
  ok "Playwright Chromium"
else
  warn "playwright install chromium failed — run manually: python3 -m playwright install chromium"
fi

# ── pre-commit hooks ──────────────────────────────────────────────────────────

if [[ "$INSTALL_DEV" == true ]] && need pre-commit; then
  log "Installing pre-commit hooks…"
  run pre-commit install --install-hooks && ok "pre-commit hooks"
fi

# ── Claude Code CLI ───────────────────────────────────────────────────────────

log "Checking Claude Code CLI…"

if need claude; then
  ok "claude (already installed)"
else
  if is_mac; then
    log "Installing Claude Code via Salesforce installer…"
    echo "    The installer will open a browser tab for Google authentication."
    echo "    Sign in with your @salesforce.com account, then return here."
    echo ""
    if curl -fsSL https://plugins.codegen.salesforceresearch.ai/claude/install.sh | bash; then
      # Reload PATH so the claude binary is findable in this shell session
      if [[ -f "$HOME/.zshrc" ]]; then
        # shellcheck source=/dev/null
        source "$HOME/.zshrc" 2>/dev/null || true
      elif [[ -f "$HOME/.bashrc" ]]; then
        # shellcheck source=/dev/null
        source "$HOME/.bashrc" 2>/dev/null || true
      fi
      need claude && ok "claude" || \
        warn "claude installed but not yet in PATH — open a new terminal to use it"
    else
      warn "Claude Code install failed — run manually: curl -fsSL https://plugins.codegen.salesforceresearch.ai/claude/install.sh | bash"
    fi
  else
    warn "Claude Code auto-install is macOS only — see your IT portal for Linux instructions"
  fi
fi

# ── Claude Code slash commands ────────────────────────────────────────────────

log "Installing Claude Code slash commands…"

SOURCE_DIR="$SCRIPT_DIR/.claude/commands"
DEST_DIR="$HOME/.claude/commands"

if [[ ! -d "$SOURCE_DIR" ]]; then
  warn ".claude/commands/ not found in $SCRIPT_DIR — skipping slash command install"
else
  mkdir -p "$DEST_DIR"
  count=0
  for file in "$SOURCE_DIR"/*.md; do
    [[ -f "$file" ]] || continue
    cp "$file" "$DEST_DIR/$(basename "$file")"
    ok "/$(basename "$file" .md)"
    count=$((count + 1))
  done
  [[ "$count" -gt 0 ]] && log "$count slash command(s) installed to $DEST_DIR"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "Setup complete."
if [[ "$INSTALL_DEV" == true ]]; then
  echo "  Runtime + dev dependencies installed."
  echo "  Run tests:        pytest tests/"
  echo "  Run BATS CI tests: bats tests/test_ci_shell.bats"
else
  echo "  Runtime dependencies installed."
  echo "  Re-run with --dev to also install test/lint tooling."
fi
echo "  Start a new Claude Code session to use the slash commands."
echo ""
