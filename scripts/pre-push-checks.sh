#!/usr/bin/env bash
set -euo pipefail

# Pre-push validation script
# Run manually or wire into git pre-push hook

echo "[INFO] Running pre-push checks..."

# 1. Lint
echo "[INFO] Checking lint..."
ruff check clickwheel/
ruff format --check clickwheel/

# 2. Tests with coverage
echo "[INFO] Running tests with coverage..."
python -m pytest tests/ -v --tb=short

# 3. Shell scripts
echo "[INFO] Checking shell scripts..."
shellcheck scripts/*.sh
shfmt -d scripts/*.sh

# 4. Check for debug artifacts
echo "[INFO] Checking for debug artifacts..."
if grep -rn "breakpoint()" clickwheel/ --include="*.py" 2>/dev/null; then
    echo "[ERROR] Found breakpoint() calls. Remove before pushing."
    exit 1
fi
if grep -rn "import pdb" clickwheel/ --include="*.py" 2>/dev/null; then
    echo "[ERROR] Found pdb imports. Remove before pushing."
    exit 1
fi

echo "[SUCCESS] All pre-push checks passed."
