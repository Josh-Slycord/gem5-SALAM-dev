#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Generate commit-pinned provenance and license inventory for candidate upstream files."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CANDIDATE_PREFIXES = (
    "src/hwacc",
    "configs/SALAM",
    "SALAM-Configurator",
    "tools/SALAM-Configurator",
    "tools/hw_generator",
    "tools/cacti-SALAM",
    "benchmarks/common",
    "SALAMClassGenerator.py",
    "HWProfileGenerator.py",
    "SALAMArgs.py",
)

SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*([^\s*#\n\r]+)")
COPYRIGHT_RE = re.compile(
    r"(?:Copyright\s+(?:\([cC]\)\s*)?(?:[0-9]{4}(?:-[0-9]{4})?,\s*)*(?:[^\n\r*#/]+))",
    re.IGNORECASE,
)


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def get_git_file_log(repo_root, rel_path, pinned_commit):
    try:
        # First commit
        earliest_raw = subprocess.check_output(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "log", "--reverse", "--format=%H|%an|%ae|%ad|%s", "--date=iso", pinned_commit, "--", rel_path],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace").strip().splitlines()
        
        # Latest commit
        latest_raw = subprocess.check_output(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "log", "-n", "1", "--format=%H|%an|%ae|%ad|%s", "--date=iso", pinned_commit, "--", rel_path],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace").strip().splitlines()

        count_raw = subprocess.check_output(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "rev-list", "--count", pinned_commit, "--", rel_path],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace").strip()

        commit_count = int(count_raw) if count_raw.isdigit() else 0
        earliest = earliest_raw[0].split("|") if earliest_raw else []
        latest = latest_raw[0].split("|") if latest_raw else []

        return {
            "commit_count": commit_count,
            "earliest_commit": {
                "hash": earliest[0] if len(earliest) > 0 else None,
                "author": earliest[1] if len(earliest) > 1 else None,
                "email": earliest[2] if len(earliest) > 2 else None,
                "date": earliest[3] if len(earliest) > 3 else None,
                "subject": earliest[4] if len(earliest) > 4 else None,
            },
            "latest_commit": {
                "hash": latest[0] if len(latest) > 0 else None,
                "author": latest[1] if len(latest) > 1 else None,
                "email": latest[2] if len(latest) > 2 else None,
                "date": latest[3] if len(latest) > 3 else None,
                "subject": latest[4] if len(latest) > 4 else None,
            },
        }
    except Exception as e:
        return {"error": str(e), "commit_count": 0}


def classify_provenance(rel_path, earliest_author, earliest_subject, content):
    lower_path = rel_path.lower()
    lower_author = (earliest_author or "").lower()
    lower_subject = (earliest_subject or "").lower()

    if "cacti" in lower_path:
        return "third_party_cacti"
    if "kaiserslautern" in content.lower() or "matthias jung" in content.lower():
        return "third_party_kaiserslautern"
    if any(k in lower_path for k in ["response_queue.hh", "float_bits.hh", "fu_scheduling_pool.test.cc", "verify_native_stats.py", "native_helpers", "guest_uart_regression"]):
        return "fork_addition"
    if "akanksha" in lower_author or "akanksha" in lower_subject:
        return "pr2429_akanksha"
    if any(k in lower_author for k in ["josh", "slycord"]):
        return "fork_addition"
    if any(k in content.lower() for k in ["charlotte", "uncc", "salam"]):
        return "uncc_salam"
    if any(k in content.lower() for k in ["regents of the university of california", "gem5"]):
        return "gem5_core_or_derived"
    return "unresolved_attribution"


def audit_files(repo_root=REPO_ROOT, pinned_commit="f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb"):
    repo_root = Path(repo_root).resolve(strict=True)
    all_files = subprocess.check_output(
        ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "ls-tree", "-r", "--name-only", pinned_commit],
        cwd=str(repo_root),
    ).decode("utf-8").splitlines()

    candidate_files = [
        f for f in all_files
        if any(f == p or f.startswith(p + "/") for p in CANDIDATE_PREFIXES)
    ]

    inventory = []
    classifications = Counter()
    missing_spdx_list = []
    missing_copyright_list = []
    duplicate_copies = []

    for rel_path in sorted(candidate_files):
        abs_path = repo_root / rel_path
        if not abs_path.is_file():
            continue

        try:
            content = abs_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            content = ""

        # Extract SPDX
        spdx_match = SPDX_RE.search(content)
        spdx_id = spdx_match.group(1).strip() if spdx_match else None

        # Extract Copyright notices
        copyright_matches = [m.group(0).strip() for m in COPYRIGHT_RE.finditer(content[:4096])]
        # Clean up lines
        cleaned_copyrights = []
        for cr in copyright_matches:
            # strip leading comment characters
            cr_clean = re.sub(r"^[\s*#/]+", "", cr).strip()
            if len(cr_clean) > 9 and cr_clean not in cleaned_copyrights:
                cleaned_copyrights.append(cr_clean)

        git_log = get_git_file_log(repo_root, rel_path, pinned_commit)
        earliest_author = (git_log.get("earliest_commit") or {}).get("author")
        earliest_subject = (git_log.get("earliest_commit") or {}).get("subject")

        prov_class = classify_provenance(rel_path, earliest_author, earliest_subject, content)
        classifications[prov_class] += 1

        flags = []
        if not spdx_id:
            flags.append("missing_spdx")
            missing_spdx_list.append(rel_path)
        if not cleaned_copyrights:
            flags.append("missing_copyright")
            missing_copyright_list.append(rel_path)

        # Duplicate copy checks
        if rel_path.startswith("SALAM-Configurator/") and (repo_root / ("tools/" + rel_path)).is_file():
            flags.append("duplicate_in_tools_salam_configurator")
            duplicate_copies.append((rel_path, "tools/" + rel_path))
        if rel_path in ("SALAMClassGenerator.py", "HWProfileGenerator.py", "SALAMArgs.py") and (repo_root / f"tools/hw_generator/{rel_path}").is_file():
            flags.append("duplicate_in_tools_hw_generator")
            duplicate_copies.append((rel_path, f"tools/hw_generator/{rel_path}"))

        entry = {
            "path": rel_path,
            "bytes": abs_path.stat().st_size,
            "sha256": file_sha256(abs_path),
            "spdx_id": spdx_id,
            "copyright_notices": cleaned_copyrights,
            "provenance_class": prov_class,
            "git_log": git_log,
            "flags": flags,
        }
        inventory.append(entry)

    summary = {
        "pinned_commit": pinned_commit,
        "total_candidate_files": len(inventory),
        "classification_breakdown": dict(classifications),
        "spdx_present": sum(1 for e in inventory if e["spdx_id"] is not None),
        "spdx_missing": len(missing_spdx_list),
        "copyright_present": sum(1 for e in inventory if e["copyright_notices"]),
        "copyright_missing": len(missing_copyright_list),
        "duplicate_copies_count": len(duplicate_copies),
        "unresolved_ownership_notes": [
            "Original UNCC SALAM repository (2018-2022) had blanket or implicit BSD/MIT-style licensing across many generated and core files without per-file SPDX-License-Identifier tags.",
            "Files under tools/cacti-SALAM retain third-party CACTI (HP Labs) heritage with distinct licensing terms.",
            "Files under benchmarks/common (syscalls.c, Makefile) originate from TU Kaiserslautern bare-metal ARM test suites (Matthias Jung, Frederik Lauer).",
            "Duplicated configurator scripts exist in both root (SALAM-Configurator/) and tools/ (tools/SALAM-Configurator/, tools/hw_generator/).",
            "This inventory establishes current file provenance and identified gaps; it does not constitute legal clearance or assign maintainer commitments."
        ]
    }

    return {"summary": summary, "files": inventory}


def render_markdown_report(audit_result):
    summary = audit_result["summary"]
    files = audit_result["files"]

    lines = [
        "# Candidate Upstream Provenance & License Inventory",
        "",
        f"**Audit Snapshot Date:** 5 November 2026  ",
        f"**Pinned Code Commit:** `{summary['pinned_commit']}` (`gem5-26-integration-checkpoint-20261105`)  ",
        f"**Candidate Scope:** Simulator core (`src/hwacc/`), configurations (`configs/SALAM/`), configurators (`SALAM-Configurator/`, `tools/`), generators, and bare-metal runtime (`benchmarks/common/`).",
        "",
        "> [!IMPORTANT]",
        "> This audit is an initial commit-pinned inventory of file origins, copyright headers, and license tags. It identifies provenance facts and open gaps; it does not constitute legal license clearance or assert maintainer commitments.",
        "",
        "## Summary Metrics",
        "",
        f"- **Total candidate files audited:** {summary['total_candidate_files']}",
        f"- **Files with explicit SPDX tags:** {summary['spdx_present']} / {summary['total_candidate_files']} ({summary['spdx_missing']} missing)",
        f"- **Files with copyright notices:** {summary['copyright_present']} / {summary['total_candidate_files']} ({summary['copyright_missing']} missing)",
        f"- **Duplicate tree copies flagged:** {summary['duplicate_copies_count']}",
        "",
        "### Provenance Classification Breakdown",
        "",
        "| Classification | File Count | Description |",
        "|---|---|---|",
    ]

    descriptions = {
        "uncc_salam": "Original UNC Charlotte SALAM research files (Sam Rogers et al.)",
        "gem5_core_or_derived": "Mainline gem5 SimObject bases or direct derivatives (UC Regents, AMD, ARM)",
        "pr2429_akanksha": "Upstream gem5 PR #2429 author additions (@akanksha-sc)",
        "third_party_cacti": "CACTI memory model tooling (HP Labs / third-party)",
        "third_party_kaiserslautern": "Bare-metal ARM runtime support (TU Kaiserslautern)",
        "fork_addition": "New files authored in this fork (Josh-Slycord/gem5-SALAM-dev)",
        "unresolved_attribution": "Files with ambiguous, mixed, or missing authorship records",
    }

    for cat, count in sorted(summary["classification_breakdown"].items()):
        lines.append(f"| `{cat}` | {count} | {descriptions.get(cat, '')} |")

    lines.extend([
        "",
        "## Open Licensing, Attribution & Maintainer Boundaries",
        "",
    ])
    for note in summary["unresolved_ownership_notes"]:
        lines.append(f"- {note}")

    lines.extend([
        "",
        "## High-Priority Candidate Files Entering Upstream Series",
        "",
        "| Path | Bytes | SHA-256 (Prefix) | SPDX | Provenance Class | Earliest Author | Flags |",
        "|---|---|---|---|---|---|---|",
    ])

    # Prioritize non-generated C++, Python SimObjects, and Configurator scripts
    priority_files = [
        f for f in files
        if not "/generated/" in f["path"] and f["path"].endswith((".cc", ".hh", ".py", ".c", ".h"))
    ]

    for f in priority_files:
        sha_short = f["sha256"][:12]
        spdx_str = f"`{f['spdx_id']}`" if f["spdx_id"] else "**MISSING**"
        earliest_author = (f["git_log"].get("earliest_commit") or {}).get("author") or "Unknown"
        flags_str = ", ".join(f["flags"]) if f["flags"] else "Clean"
        lines.append(f"| `{f['path']}` | {f['bytes']} | `{sha_short}` | {spdx_str} | `{f['provenance_class']}` | {earliest_author} | {flags_str} |")

    lines.extend([
        "",
        "## Complete Inventory Reference",
        "",
        "The full machine-readable inventory with per-file commit hashes and copyright strings is recorded in [PROVENANCE_INVENTORY_2026-11-05.json](PROVENANCE_INVENTORY_2026-11-05.json).",
        "",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--commit", default="f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb")
    parser.add_argument("--output-json", default=str(REPO_ROOT / "workbench/docs/PROVENANCE_INVENTORY_2026-11-05.json"))
    parser.add_argument("--output-md", default=str(REPO_ROOT / "workbench/docs/PROVENANCE_INVENTORY_2026-11-05.md"))
    args = parser.parse_args()

    result = audit_files(args.repo_root, args.commit)
    
    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    md_content = render_markdown_report(result)
    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"Wrote JSON inventory to {args.output_json}")
    print(f"Wrote Markdown report to {args.output_md}")
    print(f"Total candidate files audited: {result['summary']['total_candidate_files']}")


if __name__ == "__main__":
    main()
