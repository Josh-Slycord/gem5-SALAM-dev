#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Inventory exact Git blobs and observed notices, without assigning rights.

Paths, contents, sizes, modes and duplicate-copy facts all come from one
resolved commit. Worktree files never supply candidate content. Path history
and token/name classifications are explicitly unverified origin hints;
they are not copyright ownership, governing-license or clearance decisions.
"""
import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMMIT = "f3f437a29bcd1f1cf94a4bafdedcc43f577d3feb"
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
SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*([^\r\n]+)")
COPYRIGHT_RE = re.compile(
    r"(?:Copyright\s+(?:\([cC]\)\s*)?"
    r"(?:[0-9]{4}(?:-[0-9]{4})?,\s*)*(?:[^\n\r*#/]+))",
    re.IGNORECASE,
)
HINT_DESCRIPTIONS = {
    "cacti_path_hint": "Path mentions CACTI; source origin and rights unverified",
    "kaiserslautern_text_hint": "Observed name/place token; origin and rights unverified",
    "fork_specific_path_hint": "Known fork-specific path spelling; authorship unverified",
    "pr2429_author_or_subject_hint": "Path-history name/subject hint; authorship unverified",
    "fork_author_name_hint": "Path-history author-name hint; source authorship unverified",
    "salam_text_hint": "Text mentions SALAM/UNCC; original ownership unverified",
    "gem5_text_hint": "Text mentions gem5/UC Regents; governing terms unverified",
    "no_hint": "No selected heuristic matched; attribution remains unverified",
}
OPEN_NOTES = (
    "Observed SPDX strings and copyright notices are transcribed evidence, "
    "not governing-license or compatibility determinations.",
    "A path-history author or file-introduction commit does not establish "
    "original source authorship or copyright ownership.",
    "Heuristic origin hints may describe mixed or derived files and must "
    "not be used as legal attribution or clearance.",
    "No blanket UNCC BSD/MIT scope, university ownership, CACTI ownership, "
    "or maintainer commitment is inferred by this scan.",
    "Root licenses and source-specific obligations require separate "
    "evidence review; absence of a per-file tag does not mean no license.",
)


def _git(repo_root, *args):
    return subprocess.check_output(
        [
            "git",
            "--literal-pathspecs",
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(repo_root),
            *args,
        ],
        stderr=subprocess.PIPE,
    )


def _resolve_commit(repo_root, requested):
    value = (
        _git(
            repo_root,
            "rev-parse",
            "--verify",
            "--end-of-options",
            str(requested) + "^{commit}",
        )
        .decode("ascii")
        .strip()
    )
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
        raise ValueError("Git did not resolve an immutable commit identity")
    return value


def _tree_entries(repo_root, commit):
    entries = {}
    for raw in _git(repo_root, "ls-tree", "-r", "-z", "--full-tree", commit).split(
        b"\0"
    ):
        if not raw:
            continue
        metadata, path = raw.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split()
        name = path.decode("utf-8", errors="surrogateescape")
        entries[name] = {"mode": mode, "type": kind, "object": object_id}
    return entries


def get_git_file_log(repo_root, rel_path, pinned_commit):
    """Report path-scoped Git records; do not claim rename/original authorship."""
    raw = _git(
        repo_root,
        "log",
        "--reverse",
        "-z",
        "--format=%H%x00%an%x00%ae%x00%aI%x00%s",
        pinned_commit,
        "--",
        rel_path,
    )
    framed = raw[:-1] if raw.endswith(b"\0") else raw
    fields = framed.split(b"\0") if framed else []
    if len(fields) % 5:
        raise ValueError("Unexpected Git path-history record framing")
    records = []
    for offset in range(0, len(fields), 5):
        record = [
            value.decode("utf-8", errors="replace")
            for value in fields[offset : offset + 5]
        ]
        records.append(
            dict(zip(("hash", "author", "email", "date", "subject"), record))
        )
    return {
        "commit_count": len(records),
        "history_scope": "git_log_for_current_path_at_pinned_commit",
        "renames_followed": False,
        "original_authorship_established": False,
        "earliest_commit": records[0] if records else {},
        "latest_commit": records[-1] if records else {},
    }


def classify_provenance(rel_path, earliest_author, earliest_subject, content):
    """Return only an unverified search hint; never infer ownership or a license."""
    lower_path = rel_path.lower()
    lower_author = (earliest_author or "").lower()
    lower_subject = (earliest_subject or "").lower()
    lower_content = content.lower()
    if "cacti" in lower_path:
        return "cacti_path_hint"
    if "kaiserslautern" in lower_content or "matthias jung" in lower_content:
        return "kaiserslautern_text_hint"
    if any(
        token in lower_path
        for token in (
            "response_queue.hh",
            "float_bits.hh",
            "fu_scheduling_pool.test.cc",
            "verify_native_stats.py",
            "native_helpers",
            "guest_uart_regression",
        )
    ):
        return "fork_specific_path_hint"
    if "akanksha" in lower_author or "akanksha" in lower_subject:
        return "pr2429_author_or_subject_hint"
    if any(token in lower_author for token in ("josh", "slycord")):
        return "fork_author_name_hint"
    if any(token in lower_content for token in ("charlotte", "uncc", "salam")):
        return "salam_text_hint"
    if any(
        token in lower_content
        for token in (
            "regents of the university of california",
            "gem5",
        )
    ):
        return "gem5_text_hint"
    return "no_hint"


def _notices(data, regular):
    if not regular:
        return "", None, [], "not_scanned_symlink_or_nonregular"
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        return "", None, [], "not_scanned_non_utf8"
    match = SPDX_RE.search(content)
    expression = match.group(1).split("*/", 1)[0].strip() if match else None
    notices = []
    for match in COPYRIGHT_RE.finditer(content[:4096]):
        value = re.sub(r"^[\s*#/]+", "", match.group(0)).strip()
        if len(value) > 9 and value not in notices:
            notices.append(value)
    return content, expression, notices, "utf8_blob_notice_scan"


def audit_files(repo_root=REPO_ROOT, pinned_commit=DEFAULT_COMMIT):
    repo_root = Path(repo_root).resolve(strict=True)
    commit = _resolve_commit(repo_root, pinned_commit)
    tree = _tree_entries(repo_root, commit)
    candidates = {
        path: entry
        for path, entry in tree.items()
        if any(
            path == prefix or path.startswith(prefix + "/")
            for prefix in CANDIDATE_PREFIXES
        )
    }
    inventory, duplicates = [], []
    for rel_path, entry in sorted(candidates.items()):
        if entry["type"] != "blob":
            inventory.append(
                {
                    "path": rel_path,
                    "git_object": entry["object"],
                    "git_mode": entry["mode"],
                    "git_type": entry["type"],
                    "validation_status": "non_blob_entry_not_content_audited",
                    "attribution_status": "unverified",
                    "rights_status": "not_evaluated",
                }
            )
            continue
        data = _git(repo_root, "cat-file", "blob", entry["object"])
        regular = entry["mode"] in ("100644", "100755")
        content, expression, notices, scan = _notices(data, regular)
        history = get_git_file_log(repo_root, rel_path, commit)
        earliest = history["earliest_commit"]
        hint = classify_provenance(
            rel_path, earliest.get("author"), earliest.get("subject"), content
        )
        flags = []
        if scan != "utf8_blob_notice_scan":
            flags.append(scan)
        else:
            if not expression:
                flags.append("no_spdx_tag_detected")
            if not notices:
                flags.append("no_copyright_notice_detected_in_first_4096_chars")
        duplicate = None
        if rel_path.startswith("SALAM-Configurator/"):
            duplicate = "tools/" + rel_path
        elif rel_path in (
            "SALAMClassGenerator.py",
            "HWProfileGenerator.py",
            "SALAMArgs.py",
        ):
            duplicate = "tools/hw_generator/" + rel_path
        if duplicate in tree:
            pair = {
                "first": rel_path,
                "second": duplicate,
                "same_git_object": entry["object"] == tree[duplicate]["object"],
            }
            duplicates.append(pair)
            flags.append("corresponding_tree_path_exists")
        inventory.append(
            {
                "path": rel_path,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "git_blob": entry["object"],
                "git_mode": entry["mode"],
                "git_type": entry["type"],
                "notice_scan": scan,
                "spdx_expression": expression,
                "copyright_notices": notices,
                "provenance_hint": hint,
                "attribution_status": "unverified",
                "rights_status": "not_evaluated",
                "git_log": history,
                "flags": flags,
            }
        )
    blobs = [item for item in inventory if "sha256" in item]
    text = [item for item in blobs if item["notice_scan"] == "utf8_blob_notice_scan"]
    hints = Counter(item["provenance_hint"] for item in blobs)
    summary = {
        "requested_revision": str(pinned_commit),
        "pinned_commit": commit,
        "source_of_all_candidate_bytes": "git_blob_at_resolved_commit",
        "worktree_content_consulted": False,
        "candidate_prefixes": list(CANDIDATE_PREFIXES),
        "total_candidate_entries": len(inventory),
        "total_candidate_files": len(blobs),
        "text_files_notice_scanned": len(text),
        "unscanned_non_blob_entries": len(inventory) - len(blobs),
        "heuristic_hint_breakdown": dict(sorted(hints.items())),
        "spdx_present": sum(item["spdx_expression"] is not None for item in text),
        "spdx_not_detected": sum(item["spdx_expression"] is None for item in text),
        "copyright_present": sum(bool(item["copyright_notices"]) for item in text),
        "copyright_not_detected": sum(not item["copyright_notices"] for item in text),
        "corresponding_tree_paths": duplicates,
        "duplicate_path_pairs": len(duplicates),
        "byte_identical_duplicate_pairs": sum(
            item["same_git_object"] for item in duplicates
        ),
        "unresolved_ownership_notes": list(OPEN_NOTES),
    }
    return {
        "schema_version": 2,
        "kind": "candidate_git_blob_notice_inventory",
        "validation_status": {
            "blob_identity": "verified_against_resolved_git_objects",
            "attribution": "unverified_heuristic_hints_only",
            "governing_license": "not_determined",
            "legal_clearance": "not_performed",
            "history": "path_scoped_without_rename_following",
        },
        "summary": summary,
        "files": inventory,
    }


def _cell(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _code(value):
    tick = chr(96)
    return tick + _cell(value).replace(tick, "'") + tick


def render_markdown_report(
    audit_result, inventory_name="PROVENANCE_INVENTORY_CURRENT.json"
):
    summary = audit_result["summary"]
    lines = [
        "# Candidate Git-blob notices and provenance hints",
        "",
        "**Resolved source commit:** " + _code(summary["pinned_commit"]),
        "",
        "All listed content, byte counts, modes and hashes come from that "
        "commit's Git objects. Dirty, missing, untracked or symlinked worktree "
        "copies do not supply candidate content.",
        "",
        "> Origin hints are unverified search aids. Git path authors are not "
        "asserted copyright holders, and detected notices do not establish "
        "governing terms or legal clearance.",
        "",
        "## Recorded scope",
        "",
        "Candidate prefixes: "
        + ", ".join(_code(p) for p in summary["candidate_prefixes"]),
        "",
        "- Candidate tree entries: " + str(summary["total_candidate_entries"]),
        "- Content-audited Git blobs: " + str(summary["total_candidate_files"]),
        "- UTF-8 files scanned for notices: "
        + str(summary["text_files_notice_scanned"]),
        "- SPDX strings detected: " + str(summary["spdx_present"]),
        "- Copyright strings detected in the first 4096 characters: "
        + str(summary["copyright_present"]),
        "- Corresponding root/tools path pairs: "
        + str(summary["duplicate_path_pairs"])
        + " ("
        + str(summary["byte_identical_duplicate_pairs"])
        + " identical Git objects)",
        "",
        "These counts describe detected evidence. A missing per-file tag is "
        "not a finding that a file is unlicensed.",
        "",
        "## Unverified heuristic hints",
        "",
        "| Hint | Count | Meaning |",
        "| --- | --- | --- |",
    ]
    for hint, count in summary["heuristic_hint_breakdown"].items():
        lines.append(
            "| {} | {} | {} |".format(
                _code(hint), count, _cell(HINT_DESCRIPTIONS[hint])
            )
        )
    lines.extend(["", "## Unresolved rights and attribution", ""])
    lines.extend("- " + note for note in summary["unresolved_ownership_notes"])
    lines.extend(
        [
            "",
            "Path-history records use the current filename without rename following. "
            "They record Git metadata at the pin, not verified file creation or "
            "original authorship.",
            "",
            "## Candidate blob inventory",
            "",
            "| Path | Bytes | SHA-256 | Observed SPDX text | Unverified hint | Earliest reported path-commit author | Flags |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in audit_result["files"]:
        if "sha256" not in item:
            lines.append(
                "| {} | - | - | Not scanned | Non-blob entry | - | {} |".format(
                    _code(item["path"]), _cell(item["validation_status"])
                )
            )
            continue
        author = item["git_log"]["earliest_commit"].get("author") or "No path record"
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                _code(item["path"]),
                item["bytes"],
                _code(item["sha256"]),
                _code(item["spdx_expression"])
                if item["spdx_expression"]
                else "Not detected",
                _code(item["provenance_hint"]),
                _cell(author),
                _cell(", ".join(item["flags"])) or "No scanner flags",
            )
        )
    lines.extend(
        [
            "",
            "The complete machine-readable record is ["
            + _cell(inventory_name)
            + "]("
            + inventory_name.replace(" ", "%20")
            + ").",
            "",
            "Symlink blobs are hashed as stored link data and are never followed. "
            "Non-UTF-8 blobs retain their identity but receive no text attribution "
            "scan. Detected SPDX expressions are raw strings, not validated license "
            "expressions or compatibility judgments.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--commit", default=DEFAULT_COMMIT)
    parser.add_argument(
        "--output-json",
        default=str(REPO_ROOT / "workbench/docs/PROVENANCE_INVENTORY_CURRENT.json"),
    )
    parser.add_argument(
        "--output-md",
        default=str(REPO_ROOT / "workbench/docs/PROVENANCE_INVENTORY_CURRENT.md"),
    )
    args = parser.parse_args(argv)
    result = audit_files(args.repo_root, args.commit)
    json_path, md_path = Path(args.output_json), Path(args.output_md)
    for path in (json_path, md_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    md_path.write_text(
        render_markdown_report(result, json_path.name),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "pinned_commit": result["summary"]["pinned_commit"],
                "candidate_blobs": result["summary"]["total_candidate_files"],
                "attribution": "unverified_hints_only",
                "output_json": str(json_path),
                "output_md": str(md_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
