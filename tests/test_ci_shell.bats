#!/usr/bin/env bats
#
# BATS tests for .github/scripts/ CI shell helpers.
# Run from repo root: bats tests/test_ci_shell.bats
# Requires: bats-core (brew install bats-core)

SOURCE_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"

# ── Helpers ──────────────────────────────────────────────────────────────────

setup_git_repo() {
    REPO_DIR="$(mktemp -d)"
    cd "$REPO_DIR" || return 1
    git init -q
    git config user.email "test@example.com"
    git config user.name "Test User"
    # Baseline commit so HEAD~1 is never needed
    echo "init" > README.md
    git add README.md
    git commit -qm "init"
}

teardown() {
    rm -rf "$REPO_DIR"
}

# ── detect_yaml_changes.sh ───────────────────────────────────────────────────

@test "detect_yaml_changes: outputs changed=true when commit includes a .yml file" {
    setup_git_repo
    echo "key: value" > ci.yml
    git add ci.yml
    git commit -qm "add yml"

    output_file="$BATS_TEST_TMPDIR/github_output.txt"
    run env GITHUB_OUTPUT="$output_file" \
        bash "$SOURCE_ROOT/.github/scripts/detect_yaml_changes.sh"

    [ "$status" -eq 0 ]
    grep -q "changed=true" "$output_file"
}

@test "detect_yaml_changes: outputs changed=true when commit includes a .yaml file" {
    setup_git_repo
    echo "key: value" > config.yaml
    git add config.yaml
    git commit -qm "add yaml"

    output_file="$BATS_TEST_TMPDIR/github_output.txt"
    run env GITHUB_OUTPUT="$output_file" \
        bash "$SOURCE_ROOT/.github/scripts/detect_yaml_changes.sh"

    [ "$status" -eq 0 ]
    grep -q "changed=true" "$output_file"
}

@test "detect_yaml_changes: outputs changed=false when commit has no yml/yaml files" {
    setup_git_repo
    echo "hello" > notes.txt
    git add notes.txt
    git commit -qm "add txt"

    output_file="$BATS_TEST_TMPDIR/github_output.txt"
    run env GITHUB_OUTPUT="$output_file" \
        bash "$SOURCE_ROOT/.github/scripts/detect_yaml_changes.sh"

    [ "$status" -eq 0 ]
    grep -q "changed=false" "$output_file"
}

@test "detect_yaml_changes: outputs changed=false for a .py-only commit" {
    setup_git_repo
    echo "print('hi')" > script.py
    git add script.py
    git commit -qm "add py"

    output_file="$BATS_TEST_TMPDIR/github_output.txt"
    run env GITHUB_OUTPUT="$output_file" \
        bash "$SOURCE_ROOT/.github/scripts/detect_yaml_changes.sh"

    [ "$status" -eq 0 ]
    grep -q "changed=false" "$output_file"
}

# ── sync_dev_to_main.sh ──────────────────────────────────────────────────────

setup_origin_with_main() {
    # Creates a bare origin with main, checks out dev from it
    ORIGIN_DIR="$(mktemp -d)"
    git init --bare -q "$ORIGIN_DIR"

    REPO_DIR="$(mktemp -d)"
    cd "$REPO_DIR" || return 1
    git init -q
    git config user.email "test@example.com"
    git config user.name "Test User"
    git remote add origin "$ORIGIN_DIR"

    echo "init" > README.md
    git add README.md
    git commit -qm "init"
    git branch -M main
    git push -q origin main

    git checkout -q -b dev
    git push -q -u origin dev
}

@test "sync_dev_to_main: no-ops when dev is up to date with main" {
    setup_origin_with_main

    run bash "$SOURCE_ROOT/.github/scripts/sync_dev_to_main.sh"

    [ "$status" -eq 0 ]
    [[ "$output" == *"up to date"* ]]
}

@test "sync_dev_to_main: fast-forwards dev when dev is behind and has no local commits" {
    setup_origin_with_main

    # Add a commit to main on origin (simulates a merged PR)
    WORK_DIR="$(mktemp -d)"
    git clone -q "$ORIGIN_DIR" "$WORK_DIR"
    cd "$WORK_DIR"
    git config user.email "test@example.com"
    git config user.name "Test User"
    git checkout -q main
    echo "merged" > merged.txt
    git add merged.txt
    git commit -qm "merge to main"
    git push -q origin main

    # Back in dev repo — dev is now behind main, 0 ahead
    cd "$REPO_DIR"
    run bash "$SOURCE_ROOT/.github/scripts/sync_dev_to_main.sh"

    [ "$status" -eq 0 ]
    [[ "$output" == *"fast-forwarding"* ]]
    rm -rf "$WORK_DIR"
}

@test "sync_dev_to_main: reports diverged when dev is both behind and ahead of main" {
    setup_origin_with_main

    # Commit on dev (ahead)
    echo "dev work" > dev_change.txt
    git add dev_change.txt
    git commit -qm "dev work"

    # Commit on main via origin (behind)
    WORK_DIR="$(mktemp -d)"
    git clone -q "$ORIGIN_DIR" "$WORK_DIR"
    cd "$WORK_DIR" || return 1
    git config user.email "test@example.com"
    git config user.name "Test User"
    git checkout -q main
    echo "main work" > main_change.txt
    git add main_change.txt
    git commit -qm "main work"
    git push -q origin main

    cd "$REPO_DIR" || return 1
    run bash "$SOURCE_ROOT/.github/scripts/sync_dev_to_main.sh"

    [ "$status" -eq 0 ]
    [[ "$output" == *"diverged"* ]]
    rm -rf "$WORK_DIR"
}

# ── create_or_skip_pr.sh ─────────────────────────────────────────────────────
#
# This script calls `gh` (GitHub CLI) which requires a live GitHub token and
# network access. We test the pure-bash guard logic by stubbing `gh` with a
# local function that returns controlled output, bypassing the network entirely.

@test "create_or_skip_pr: skips when dev has no commits ahead of main" {
    setup_git_repo

    # Stub gh: ahead_by=0 means dev is not ahead
    mkdir -p "$BATS_TEST_TMPDIR/bin"
    cat > "$BATS_TEST_TMPDIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
# Minimal gh stub — only handles the compare API call
if [[ "$*" == *"compare"* ]]; then echo "0"; fi
EOF
    chmod +x "$BATS_TEST_TMPDIR/bin/gh"

    run env PATH="$BATS_TEST_TMPDIR/bin:$PATH" \
        GITHUB_REPOSITORY="owner/repo" \
        bash "$SOURCE_ROOT/.github/scripts/create_or_skip_pr.sh"

    [ "$status" -eq 0 ]
    [[ "$output" == *"no PR needed"* ]]
}

@test "create_or_skip_pr: skips PR creation when one already exists" {
    setup_git_repo

    mkdir -p "$BATS_TEST_TMPDIR/bin"
    cat > "$BATS_TEST_TMPDIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
# ahead_by=1, existing PR count=1
if [[ "$*" == *"compare"* ]]; then echo "1"
elif [[ "$*" == *"pr list"* ]]; then echo "1"
fi
EOF
    chmod +x "$BATS_TEST_TMPDIR/bin/gh"

    run env PATH="$BATS_TEST_TMPDIR/bin:$PATH" \
        GITHUB_REPOSITORY="owner/repo" \
        bash "$SOURCE_ROOT/.github/scripts/create_or_skip_pr.sh"

    [ "$status" -eq 0 ]
    [[ "$output" == *"already exists"* ]]
}

@test "create_or_skip_pr: creates PR when dev is ahead and no PR exists" {
    setup_git_repo

    mkdir -p "$BATS_TEST_TMPDIR/bin"
    cat > "$BATS_TEST_TMPDIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
# ahead_by=2, no existing PR, pr create succeeds
if [[ "$*" == *"compare"* ]]; then echo "2"
elif [[ "$*" == *"pr list"* ]]; then echo "0"
elif [[ "$*" == *"pr create"* ]]; then echo "Created PR #42"
fi
EOF
    chmod +x "$BATS_TEST_TMPDIR/bin/gh"

    run env PATH="$BATS_TEST_TMPDIR/bin:$PATH" \
        GITHUB_REPOSITORY="owner/repo" \
        bash "$SOURCE_ROOT/.github/scripts/create_or_skip_pr.sh"

    [ "$status" -eq 0 ]
    [[ "$output" == *"Created PR"* ]]
}
