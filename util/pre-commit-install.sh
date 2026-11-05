#!/bin/bash

# Copyright (c) 2022 The Regents of the University of California
# All Rights Reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
GEM5_ROOT="${DIR}/.."

cd ${GEM5_ROOT}

if command -v pre-commit &> /dev/null
then
    pre-commit install -t pre-commit -t commit-msg
else
    echo "'pre-commit' not found; installing native gem5 git hooks into .git/hooks/..."
    HOOKS_DIR="$(git rev-parse --git-path hooks)"
    mkdir -p "${HOOKS_DIR}"
    ln -sf "../../util/git-commit-msg.py" "${HOOKS_DIR}/commit-msg"
    cat > "${HOOKS_DIR}/pre-commit" << 'EOF'
#!/usr/bin/env bash
set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"
python3 util/run-git-clang-format.py --pre-commit
python3 - << 'PY'
import ast
import subprocess
import sys
from pathlib import Path

res = subprocess.run(
    ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
    capture_output=True,
    text=True,
    check=True,
)
for rel in res.stdout.splitlines():
    p = Path(rel)
    if p.suffix == ".py" and p.is_file():
        ast.parse(p.read_bytes(), filename=rel)
PY
EOF
    chmod +x "${HOOKS_DIR}/pre-commit" "${GEM5_ROOT}/util/git-commit-msg.py"
fi
