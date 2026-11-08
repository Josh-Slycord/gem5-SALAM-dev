#!/usr/bin/env bash
# Run a saved GUI GEMM request through the supported Workbench pipeline.
set -euo pipefail
SCRIPT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORKBENCH_ROOT="$SCRIPT_ROOT/workbench"

# The historical direct systembuilder/build/guest-pass path is disabled.
# It bypassed staged generator repairs, build receipts, generated inputs and
# independent output checks. Keep its history in Git; use the checked runner.
if [[ $# -eq 0 ]]; then
    cat <<'HELP'
Usage: ./run_gemm.sh --request /absolute/path/to/request.json [--jobs 1..32]
Use a generated-input GEMM request saved by a Workbench run.
Settings regenerate/rebuild through the normal pipeline when required.
Timelines are derived exports; accepted raw evidence is never overwritten.
A valid workspace.json and verified external runtime are required.
HELP
    exit 2
fi

if [[ -z "${SALAM_PYTHON:-}" ]]; then
    SALAM_PYTHON="$(cd "$WORKBENCH_ROOT" && python3 -c \
      'from salam_workbench.toolchain_profile import load_toolchain; print(load_toolchain()["python"])')"
fi
if [[ ! -x "$SALAM_PYTHON" ]]; then
    printf 'Selected Workbench Python is unavailable: %s\n' "$SALAM_PYTHON" >&2
    exit 2
fi
cd "$WORKBENCH_ROOT"
exec "$SALAM_PYTHON" -B -m salam_workbench.configured_run --benchmark gemm "$@"
