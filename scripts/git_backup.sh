#!/bin/bash
# gem5-SALAM Git Backup with Test Results
set -e
M5_PATH="${M5_PATH:-/home/jslycord/gem5-SALAM-dev}"
cd "$M5_PATH"

echo "======================================"
echo "gem5-SALAM Git Backup Workflow"
echo "======================================"

RUN_TESTS=false
MESSAGE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --test|-t) RUN_TESTS=true; shift ;;
        --message|-m) MESSAGE="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [ -z "$(git status --porcelain)" ]; then
    echo "No changes to commit."
    exit 0
fi

TEST_STATUS=""
if [ "$RUN_TESTS" = true ]; then
    echo "Running tests..."
    if python3 scripts/run_tests.py; then
        TEST_STATUS="PASS"
        echo "Tests passed!"
    else
        TEST_STATUS="FAIL"
        echo "Some tests failed - see TEST_RESULTS.md"
    fi
    git add TEST_RESULTS.md test_results.json 2>/dev/null || true
fi

DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M:%S)
VERSION="v$(date +%Y%m%d.%H%M)"

echo ""
echo "Changes to commit:"
git status --short | head -20

if [ -z "$MESSAGE" ]; then
    COUNT=$(git status --short | wc -l)
    MESSAGE="Backup: $COUNT files changed"
    [ -n "$TEST_STATUS" ] && MESSAGE="$MESSAGE [Tests: $TEST_STATUS]"
fi

echo ""
echo "Commit message: $MESSAGE"

git add -A
git commit -m "$MESSAGE

Backup created: $DATE $TIME
Version tag: $VERSION"

echo ""
echo "Committed successfully!"
git log -1 --oneline