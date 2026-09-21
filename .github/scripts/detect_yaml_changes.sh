#!/usr/bin/env bash
# Outputs GITHUB_OUTPUT key `changed=true/false` based on whether the current
# commit touches any .yml or .yaml files.
set -euo pipefail

output_file="${GITHUB_OUTPUT:-/dev/stdout}"

if git show --name-only --format="" HEAD | grep -qE '\.ya?ml$'; then
    echo "changed=true" >> "$output_file"
else
    echo "changed=false" >> "$output_file"
fi
