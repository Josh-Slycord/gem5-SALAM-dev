# SPDX-License-Identifier: BSD-3-Clause
"""Inspect changed Git object metadata without reading candidate file contents."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

MAX_BLOB_BYTES = 10 * 1024 * 1024
SHA = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
LOCAL_FILES = frozenset(
    {
        "workbench/workspace.json",
        "TEST_RESULTS.md",
        "test_results.json",
        "tests/test_results.json",
        "gem5-SALAM-gui/crash.log",
        "gem5-SALAM-gui/debug.log",
        "stats.txt",
        "simout",
        "simerr",
    }
)
LOCAL_DIRECTORIES = (
    "workbench/evidence/",
    "workbench/runs/",
    "workbench/results/",
    "workbench/releases/",
    "workbench/gui-variants/",
    "workbench/build/",
    "workbench/dist/",
    "m5out/",
    "build/",
    "gem5_build/",
    "docs/_build/",
    "src/doxygen/",
    "cacti-salam/results/",
    "ext/mcpat/results/",
)
CACHE_COMPONENTS = frozenset({"__pycache__", ".venv", ".pytest_cache", ".mypy_cache"})
COMPILED_SUFFIXES = frozenset(
    {".o", ".elf", ".bc", ".pyc", ".pyo", ".vhdx", ".qcow2", ".bundle"}
)


class HygieneError(ValueError):
    """Git metadata or the requested comparison could not be verified."""


def _git(repo, *args):
    # Preserve GIT_INDEX_FILE: a pre-commit invocation may select its own index.
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    result = subprocess.run(
        [
            "git",
            "--literal-pathspecs",
            "--no-optional-locks",
            "--no-replace-objects",
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(repo),
            *args,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise HygieneError(
            "Git metadata command failed ({}; exit {})".format(
                args[0], result.returncode
            )
        )
    return result.stdout


def _commit(repo, value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise HygieneError("Revision must be a full hexadecimal commit ID")
    resolved = _git(repo, "rev-parse", "--verify", value + "^{commit}")
    result = resolved.decode("ascii").strip()
    if result.lower() != value.lower():
        raise HygieneError("Revision did not resolve to the requested commit")
    return result


def _path_policy(path):
    folded = path.casefold()
    parts = folded.split("/")
    local_files = {name.casefold() for name in LOCAL_FILES}
    if folded in local_files or folded.startswith(LOCAL_DIRECTORIES):
        return (
            "local-output",
            "Machine state or run output belongs outside tracked source",
        )
    if CACHE_COMPONENTS.intersection(parts):
        return "cache", "Interpreter/environment caches are local outputs"
    if PurePosixPath(path).suffix.lower() in COMPILED_SUFFIXES:
        return (
            "compiled-payload",
            "Compiled/recovery payload requires separate preservation",
        )
    return None


def _entries(raw):
    if not raw:
        return []
    fields = raw.split(b"\0")
    if fields[-1] != b"" or len(fields) % 2 != 1:
        raise HygieneError("Malformed NUL-delimited Git diff")
    entries = []
    for index in range(0, len(fields) - 1, 2):
        metadata, path_raw = fields[index : index + 2]
        columns = metadata.split()
        if len(columns) != 5 or not columns[0].startswith(b":"):
            raise HygieneError("Malformed raw Git diff metadata")
        old_mode, mode, old_oid, oid, status = columns
        del old_mode, old_oid
        mode = mode.decode("ascii")
        oid = oid.decode("ascii")
        status = status.decode("ascii")
        path = path_raw.decode("utf-8", "surrogateescape")
        if (
            status not in ("A", "M", "T")
            or mode not in ("100644", "100755", "120000", "160000")
            or not SHA.fullmatch(oid)
            or set(oid) == {"0"}
            or not path
            or path.startswith("/")
            or any(part in ("", ".", "..") for part in path.split("/"))
        ):
            raise HygieneError("Unsupported or unresolved Git diff entry")
        entries.append({"path": path, "object_id": oid, "mode": mode, "change": status})
    return entries


def audit_repository(repo, *, base=None, head=None, staged=False, merge_base=True):
    """Audit changed blobs; failures never turn into an empty successful scan."""
    report = {
        "schema_version": 1,
        "kind": "repository_hygiene",
        "state": "failed",
        "mode": "staged" if staged else "commits",
        "base_commit": None,
        "head_commit": None,
        "comparison_base": None,
        "comparison_kind": "merge-base" if merge_base else "direct",
        "max_blob_bytes": MAX_BLOB_BYTES,
        "scope": "Changed paths and Git blob sizes; no candidate content/security scan",
        "checked_files": [],
        "violations": [],
        "errors": [],
        "simulator_built": False,
        "simulator_run": False,
    }
    try:
        repo = Path(repo).resolve(strict=True)
        root = Path(
            os.fsdecode(_git(repo, "rev-parse", "--show-toplevel")).strip()
        ).resolve(strict=True)
        if root != repo:
            raise HygieneError("--repo must name the repository worktree root")
        report["repository"] = str(root)
        config_names = (
            _git(repo, "config", "--local", "--name-only", "--list")
            .decode("utf-8", "replace")
            .casefold()
            .splitlines()
        )
        if any(
            name == "extensions.partialclone"
            or (name.startswith("remote.") and name.endswith(".promisor"))
            for name in config_names
        ):
            raise HygieneError(
                "Declared partial/promisor repositories require materialized objects"
            )
        if staged:
            if base is not None or head is not None:
                raise HygieneError("--staged cannot be combined with revisions")
            base_id = _git(repo, "rev-parse", "--verify", "HEAD^{commit}")
            report["base_commit"] = base_id.decode("ascii").strip()
            report["comparison_base"] = report["base_commit"]
            args = ["--cached", report["base_commit"]]
        else:
            base_id, head_id = _commit(repo, base), _commit(repo, head)
            report["base_commit"], report["head_commit"] = base_id, head_id
            if merge_base:
                comparison = _git(repo, "merge-base", "--all", base_id, head_id)
                comparison = comparison.decode("ascii").strip()
                if not SHA.fullmatch(comparison):
                    raise HygieneError("A unique comparison merge base was not found")
            else:
                comparison = base_id
            report["comparison_base"] = comparison
            args = [comparison, head_id]
        raw = _git(
            repo,
            "diff",
            "--raw",
            "-z",
            "--no-abbrev",
            "--no-renames",
            "--no-ext-diff",
            "--no-textconv",
            "--diff-filter=AMTUXB",
            *args,
            "--",
        )
        entries = _entries(raw)
        for entry in entries:
            path = entry["path"]
            policy = _path_policy(path)
            if policy:
                report["violations"].append(
                    {"path": path, "rule": policy[0], "detail": policy[1]}
                )
            if entry["mode"] == "160000":
                entry["bytes"] = None
                entry["object_kind"] = "gitlink"
            else:
                kind = _git(repo, "cat-file", "-t", entry["object_id"])
                if kind.strip() != b"blob":
                    raise HygieneError("Changed file is not a Git blob: " + path)
                size = _git(repo, "cat-file", "-s", entry["object_id"]).strip()
                if not size.isdigit():
                    raise HygieneError("Invalid blob size for " + path)
                entry["bytes"] = int(size)
                entry["object_kind"] = "blob"
                if entry["bytes"] > MAX_BLOB_BYTES:
                    report["violations"].append(
                        {
                            "path": path,
                            "rule": "blob-size",
                            "detail": "Changed blob exceeds the reviewed 10 MiB limit",
                        }
                    )
            report["checked_files"].append(entry)
        if not report["violations"]:
            report["state"] = "passed"
    except (HygieneError, OSError, UnicodeError, subprocess.TimeoutExpired) as error:
        report["errors"].append(str(error))
    return report


def revision_pair_for_event(repo, event_name, event, current_sha):
    """Select explicit PR/push identities; new-branch/manual runs compare main."""
    if not isinstance(event, dict):
        raise HygieneError("Workflow event must be an object")
    if event_name == "pull_request":
        pull = event.get("pull_request")
        if not isinstance(pull, dict):
            raise HygieneError("Pull request identity is missing or malformed")
        base_record, head_record = pull.get("base"), pull.get("head")
        if not isinstance(base_record, dict) or not isinstance(head_record, dict):
            raise HygieneError("Pull request revisions are missing or malformed")
        base, head = base_record.get("sha"), head_record.get("sha")
    elif event_name == "push":
        head = event.get("after")
        if head != current_sha:
            raise HygieneError("Push after SHA differs from the workflow revision")
        base = event.get("before")
        if isinstance(base, str) and SHA.fullmatch(base) and set(base) == {"0"}:
            base = _git(repo, "rev-parse", "--verify", "origin/main^{commit}")
            base = base.decode("ascii").strip()
    elif event_name == "workflow_dispatch":
        head = current_sha
        base = _git(repo, "rev-parse", "--verify", "origin/main^{commit}")
        base = base.decode("ascii").strip()
    else:
        raise HygieneError("Unsupported workflow event")
    if not isinstance(base, str) or not SHA.fullmatch(base):
        raise HygieneError("Workflow base commit identity is missing or malformed")
    if not isinstance(head, str) or not SHA.fullmatch(head) or set(head) == {"0"}:
        raise HygieneError("Workflow head commit identity is missing or malformed")
    return base, head


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--github-event", type=Path)
    parser.add_argument("--event-name")
    parser.add_argument("--current-sha")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        base, head = args.base, args.head
        if args.github_event:
            if args.staged or base is not None or head is not None:
                raise HygieneError(
                    "Workflow selection cannot use staged/explicit revisions"
                )
            event = json.loads(args.github_event.read_text(encoding="utf-8"))
            if not isinstance(event, dict):
                raise HygieneError("Workflow event must be an object")
            base, head = revision_pair_for_event(
                args.repo, args.event_name, event, args.current_sha
            )
        elif args.event_name or args.current_sha:
            raise HygieneError("Workflow arguments require --github-event")
        result = audit_repository(
            args.repo,
            base=base,
            head=head,
            staged=args.staged,
            merge_base=not (args.github_event and args.event_name == "push"),
        )
    except (HygieneError, OSError, UnicodeError, ValueError) as error:
        result = {
            "schema_version": 1,
            "kind": "repository_hygiene",
            "state": "failed",
            "checked_files": [],
            "violations": [],
            "errors": [str(error)],
        }
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as stream:
                stream.write(serialized)
        except OSError:
            result["state"] = "failed"
            result["errors"].append("Could not create a fresh hygiene report")
            serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    sys.stdout.write(serialized)
    return 0 if result["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
