# SPDX-License-Identifier: BSD-3-Clause
"""Passive Git and configured-runtime status; never fetch, build or simulate.

Default remote observations are cached local refs. --live-remote asks Git for
named-remote heads without updating refs. Binary hashes are recorded evidence,
not freshly verified bytes. Git HEAD is never treated as a binary identity.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

PROJECT = Path(__file__).resolve().parents[1]
MAX_JSON_BYTES = 2 * 1024 * 1024
SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
REMOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class StatusError(ValueError):
    """A normalized diagnostic that contains no Git stderr or remote URL."""


class Git:
    def __init__(self, path, timeout=15):
        self.path = Path(path)
        self.timeout = timeout
        self._partial_clone = None
        self._shallow = None

    def run(self, *args, allow_failure=False):
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        environment.update(
            GIT_OPTIONAL_LOCKS="0",
            GIT_NO_LAZY_FETCH="1",
            GIT_TERMINAL_PROMPT="0",
            GCM_INTERACTIVE="Never",
            LC_ALL="C",
        )
        command = [
            "git",
            "--no-optional-locks",
            "--no-replace-objects",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-c",
            "gc.auto=0",
            "-c",
            "maintenance.auto=false",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-C",
            str(self.path),
        ] + list(args)
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise StatusError("Git query timed out")
        except OSError:
            raise StatusError("Git could not be executed")
        if result.returncode and not allow_failure:
            # Git errors can include credential-bearing configured URLs.
            raise StatusError("Git query failed (exit {})".format(result.returncode))
        return result

    def partial_clone(self):
        if self._partial_clone is None:
            # Key names only: never inspect configured URLs/credential values.
            result = self.run(
                "config",
                "--name-only",
                "--get-regexp",
                r"^(extensions\.partialclone|remote\..*\.promisor)$",
                allow_failure=True,
            )
            if result.returncode not in (0, 1):
                raise StatusError("Partial-clone configuration is unavailable")
            # Even a false-valued promisor key restricts inspection on old Git.
            self._partial_clone = bool(result.stdout.strip())
        return self._partial_clone

    def shallow(self):
        if self._shallow is None:
            self._shallow = self.text("rev-parse", "--is-shallow-repository") == "true"
        return self._shallow

    def text(self, *args):
        return self.run(*args).stdout.decode("utf-8", errors="replace").strip()


def _json_file(path, root):
    path, root = Path(path), Path(root).resolve()
    try:
        if path.is_symlink() or not path.is_file():
            raise StatusError("Expected a regular local JSON file")
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        # Reject directory symlinks as well as a symlinked leaf.
        cursor = path
        while cursor != root and cursor != cursor.parent:
            if cursor.is_symlink():
                raise StatusError("JSON path contains a symlink")
            cursor = cursor.parent
        if resolved.stat().st_size > MAX_JSON_BYTES:
            raise StatusError("Local JSON exceeds the status size limit")
        document = json.loads(resolved.read_text(encoding="utf-8-sig"))
        if not isinstance(document, dict):
            raise StatusError("Expected a JSON mapping")
        return document
    except StatusError:
        raise
    except (OSError, ValueError, UnicodeError):
        raise StatusError("Local JSON is unavailable or malformed")


def _evidence_path(project, value):
    if not isinstance(value, str) or "\\" in value or ":" in value:
        raise StatusError("Build receipt must be evidence-relative")
    parts = value.split("/")
    if (
        not value.startswith("evidence/")
        or any(part in ("", ".", "..") for part in parts)
        or PurePosixPath(value).is_absolute()
        or not value.endswith(".json")
    ):
        raise StatusError("Build receipt must be evidence-relative")
    return Path(project) / value


def _refs(git):
    result = {}
    partial = git.partial_clone()
    target = "" if partial else "%(*objectname)"
    fmt = "%(refname)%00%(objectname)%00" + target + "%00%(upstream)%00%(symref)"
    raw = git.run(
        "for-each-ref",
        "--format=" + fmt,
        "refs/heads",
        "refs/remotes",
        "refs/tags",
    ).stdout
    for line in raw.splitlines():
        fields = line.decode("utf-8", errors="replace").split("\0")
        if len(fields) != 5:
            raise StatusError("Malformed local ref response")
        name, object_sha, peeled, upstream, symbolic = fields
        if not SHA.fullmatch(object_sha):
            raise StatusError("Malformed local object identity")
        result[name] = {
            "sha": peeled or object_sha,
            "object_sha": object_sha,
            "peeled_sha": peeled or None,
            "tag_peeling_attempted": not partial,
            "upstream": upstream or None,
            "symbolic_target": symbolic or None,
        }
    return result


def _comparison(git, local_sha, remote_sha):
    answer = {
        "local_sha": local_sha,
        "remote_sha": remote_sha,
        "ahead_by": None,
        "behind_by": None,
        "state": "unknown",
    }
    if not local_sha or not remote_sha:
        answer["reason"] = "One of the selected refs is unavailable"
        return answer
    if local_sha == remote_sha:
        answer.update(ahead_by=0, behind_by=0, state="identical")
        return answer
    if git.partial_clone():
        answer["reason"] = "Graph traversal deferred for partial-clone safety"
        return answer
    if git.shallow():
        answer[
            "reason"
        ] = "Shallow history cannot establish complete ahead/behind counts"
        return answer
    for sha in (local_sha, remote_sha):
        if not SHA.fullmatch(sha):
            raise StatusError("Malformed comparison identity")
        if git.run("cat-file", "-e", sha + "^{commit}", allow_failure=True).returncode:
            answer["reason"] = "Selected remote object is not available locally"
            return answer
    fields = git.text(
        "rev-list", "--left-right", "--count", local_sha + "..." + remote_sha
    ).split()
    if len(fields) != 2 or not all(part.isdigit() for part in fields):
        raise StatusError("Malformed ahead/behind response")
    ahead, behind = map(int, fields)
    answer.update(
        ahead_by=ahead,
        behind_by=behind,
        state="diverged" if ahead and behind else "ahead" if ahead else "behind",
    )
    return answer


def _dirty(git, bare=False):
    if bare:
        return {"checked": False, "reason": "Bare repository has no working tree"}
    if git.partial_clone():
        return {
            "checked": False,
            "reason": "Content inspection deferred for partial-clone safety",
        }
    raw = git.run(
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=normal",
        "--ignore-submodules=all",
    ).stdout
    counts = dict(
        staged=0, unstaged=0, untracked_entries=0, conflicts=0, dirty_entries=0
    )
    entries, index = raw.split(b"\0"), 0
    unmerged = {b"DD", b"AU", b"UD", b"UA", b"DU", b"AA", b"UU"}
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4 or entry[2:3] != b" ":
            raise StatusError("Malformed worktree status")
        flag = entry[:2]
        counts["dirty_entries"] += 1
        if flag == b"??":
            counts["untracked_entries"] += 1
        else:
            counts["staged"] += int(flag[:1] != b" ")
            counts["unstaged"] += int(flag[1:] != b" ")
            counts["conflicts"] += int(flag in unmerged)
            if b"R" in flag or b"C" in flag:
                if index >= len(entries) or not entries[index]:
                    raise StatusError("Truncated rename status")
                index += 1
    return dict(
        counts,
        checked=True,
        clean=counts["dirty_entries"] == 0,
        count_scope="Porcelain entries; normal untracked directories may be grouped",
        submodule_contents="not inspected",
    )


def _worktrees(git):
    result = git.run("worktree", "list", "--porcelain", "-z", allow_failure=True)
    if result.returncode:
        # Older Git releases lack -z. Never guess quoted/escaped path spellings.
        text = git.text("worktree", "list", "--porcelain")

        if any(line.startswith('worktree "') for line in text.splitlines()):
            raise StatusError("This Git needs NUL worktree output for escaped paths")
        records = [block.splitlines() for block in text.split("\n\n") if block.strip()]
    else:
        records, record = [], []
        for value in result.stdout.decode("utf-8", errors="replace").split("\0"):
            if value:
                record.append(value)
            elif record:
                records.append(record)
                record = []
        if record:
            records.append(record)
    answer = []
    for record in records:
        item = {}
        for line in record:
            key, _, value = line.partition(" ")
            if key == "worktree":
                item["path"] = value
            elif key in ("HEAD", "branch"):
                item[key.lower()] = value
            elif key in ("bare", "detached", "locked", "prunable"):
                item[key] = value or True
        if item.get("path"):
            answer.append(item)
    return answer


def _roles(project, issues):
    path = Path(project) / "docs/git-roles.json"
    if not path.exists() and not path.is_symlink():
        return {"state": "absent", "branches": {}, "tags": {}}
    try:
        roles = _json_file(path, project)
        if roles.get("schema_version") != 1:
            raise StatusError("Unsupported Git role-map schema")
        for section in ("branches", "tags"):
            if not isinstance(roles.get(section, {}), dict):
                raise StatusError("Git role section must be a mapping")
            for name, entry in roles.get(section, {}).items():
                if not isinstance(name, str) or not isinstance(entry, dict):
                    raise StatusError("Malformed Git role entry")
                if not isinstance(entry.get("role"), str):
                    raise StatusError("Git role entry requires a role string")
                for field in ("expected_sha", "expected_object_sha"):
                    expected = entry.get(field)
                    if expected is not None and (
                        not isinstance(expected, str) or not SHA.fullmatch(expected)
                    ):
                        raise StatusError("Git role expected identity is invalid")
        return dict(roles, state="loaded", path=str(path))
    except StatusError as error:
        issues.append({"scope": "role_mapping", "message": str(error)})
        return {"state": "unavailable", "branches": {}, "tags": {}}


def _role(roles, section, name, sha, object_sha=None):
    entry = roles.get(section, {}).get(name)
    if entry is None:
        return None
    expected = entry.get("expected_sha")
    expected_object = entry.get("expected_object_sha")
    return {
        "role": entry["role"],
        "description": entry.get("description"),
        "expected_sha": expected,
        "expected_sha_matches": None
        if expected is None or sha is None
        else expected == sha,
        "expected_object_sha": expected_object,
        "expected_object_sha_matches": (
            None if expected_object is None else expected_object == object_sha
        ),
        "meaning": "Curated label; not authorship or a new qualification claim",
    }


def _live_heads(git, remote):
    if remote not in git.text("remote").splitlines():
        raise StatusError("Requested named remote is not configured")
    result = git.run(
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
        "-c",
        "protocol.ssh.allow=always",
        "ls-remote",
        "--heads",
        "--",
        remote,
    )
    heads = {}
    for line in result.stdout.decode("ascii", errors="replace").splitlines():
        fields = line.split()
        if (
            len(fields) != 2
            or not SHA.fullmatch(fields[0])
            or not fields[1].startswith("refs/heads/")
        ):
            raise StatusError("Malformed live remote-head response")
        heads[fields[1][11:]] = fields[0]
    return heads


def _runtime(project, timeout, issues, status_cache):
    workspace_path = Path(project) / "workspace.json"
    if not workspace_path.exists() and not workspace_path.is_symlink():
        return {"state": "unbound", "workspace": str(workspace_path)}
    try:
        manifest = _json_file(workspace_path, project)
        selected = manifest.get("configuration_engine")
        if not isinstance(selected, dict):
            raise StatusError("Workspace configuration engine is unavailable")
        engine_value = selected.get("path")
        if not isinstance(engine_value, str) or not engine_value:
            raise StatusError("Workspace configuration engine path is unavailable")
        engine = Path(engine_value)
        profile = selected.get("toolchain_profile")
        profile_id = profile.get("id") if isinstance(profile, dict) else profile
        result = {
            "state": "metadata_only",
            "workspace": str(workspace_path),
            "engine_path": engine_value,
            "distribution": selected.get("distribution"),
            "toolchain_profile": profile_id if isinstance(profile_id, str) else None,
            "binary_integrity_verified": False,
            "compiled_sources_verified": False,
            "head_is_binary_identity": False,
            "identity_note": (
                "Source Git HEAD and recorded build identities are separate. "
                "No simulator, source fingerprint or binary hash was verified."
            ),
        }
        if not engine.is_absolute():
            result.update(state="not_accessible", reason="Engine path is not native")
            return result
        result["engine_exists"] = engine.is_dir()
        if (engine / ".git").exists():
            source_git = Git(engine, timeout)
            head = source_git.run("rev-parse", "--verify", "HEAD", allow_failure=True)
            branch = source_git.run(
                "symbolic-ref", "--quiet", "--short", "HEAD", allow_failure=True
            )
            key = str(engine.resolve())
            if key not in status_cache:
                status_cache[key] = _dirty(source_git)
            result["source_git"] = {
                "head": head.stdout.decode().strip() if not head.returncode else None,
                "branch": branch.stdout.decode().strip()
                if not branch.returncode
                else None,
                "worktree": status_cache[key],
            }
        else:
            result["source_git"] = {"state": "no_repository_marker"}
        receipt_path = _evidence_path(project, selected.get("build_receipt"))
        receipt = _json_file(receipt_path, project)
        modern = receipt.get("kind") == "configured_engine_build"
        binary_record = (
            receipt.get("binary", {})
            if modern
            else {
                "path": receipt.get("binary_path"),
                "sha256": receipt.get("binary_sha256"),
            }
        )
        if not isinstance(binary_record, dict):
            raise StatusError("Build binary record must be a mapping")
        expected_binary = engine / "build/ARM/gem5.opt"
        recorded_path = binary_record.get("path")
        if not isinstance(recorded_path, str) or Path(recorded_path) != expected_binary:
            raise StatusError("Recorded binary path differs from selected engine")
        sha = binary_record.get("sha256")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise StatusError("Recorded binary SHA-256 is invalid")
        compiled = receipt.get("compiled_source_sha256")
        if compiled is not None and (
            not isinstance(compiled, str) or not re.fullmatch(r"[0-9a-f]{64}", compiled)
        ):
            raise StatusError("Recorded compiled-source SHA-256 is invalid")
        recorded_size = binary_record.get("bytes")
        if recorded_size is not None and (
            type(recorded_size) is not int or recorded_size < 0
        ):
            raise StatusError("Recorded binary size is invalid")
        recorded_engine = receipt.get("engine")
        if recorded_engine is not None and not isinstance(recorded_engine, str):
            raise StatusError("Recorded engine path is invalid")
        actual_size = (
            expected_binary.stat().st_size if expected_binary.is_file() else None
        )
        result["build_receipt"] = {
            "path": str(receipt_path),
            "kind": receipt.get("kind", "historical_engine_artifact"),
            "state": receipt.get("state")
            if isinstance(receipt.get("state"), str)
            else None,
            "recorded_engine": receipt.get("engine"),
            "recorded_engine_matches": (
                None
                if receipt.get("engine") is None
                else receipt["engine"] == str(engine)
            ),
            "recorded_compiled_source_sha256": compiled,
        }
        result["binary"] = {
            "path": str(expected_binary),
            "exists": expected_binary.is_file(),
            "actual_bytes": actual_size,
            "recorded_bytes": binary_record.get("bytes"),
            "recorded_sha256": sha,
            "size_matches": (
                None
                if binary_record.get("bytes") is None
                else actual_size == binary_record["bytes"]
            ),
            "hash_verification": "not_performed",
        }
        return result
    except (StatusError, OSError, ValueError, TypeError) as error:
        # Never include arbitrary decoded manifest values or parser exception text.

        message = (
            str(error)
            if isinstance(error, StatusError)
            else "Runtime metadata unavailable"
        )
        issues.append({"scope": "runtime", "message": message})
        return {"state": "unavailable", "message": message}


def inspect_status(
    repo=None,
    project=None,
    topic=None,
    remote="origin",
    all_worktrees=False,
    live_remote=False,
    timeout=15,
):
    """Collect a passive report. Dirty/ahead/behind states are data, not failures."""
    if not isinstance(remote, str) or not REMOTE.fullmatch(remote):
        raise StatusError("Remote must be a simple configured name")
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 300:
        raise StatusError("Git timeout must be finite and between 0 and 300 seconds")
    project = (
        Path(project)
        if project is not None
        else (Path(repo) / "workbench" if repo is not None else PROJECT)
    )
    project = project.resolve()
    git = Git(Path(repo).resolve() if repo is not None else PROJECT.parent, timeout)
    bare = git.text("rev-parse", "--is-bare-repository") == "true"
    root = git.path if bare else Path(git.text("rev-parse", "--show-toplevel"))
    git = Git(root, timeout)
    refs = _refs(git)
    issues = []
    roles = _roles(root / "workbench", issues)
    head_result = git.run("rev-parse", "--verify", "HEAD", allow_failure=True)
    head = head_result.stdout.decode().strip() if not head_result.returncode else None
    branch_result = git.run(
        "symbolic-ref", "--quiet", "--short", "HEAD", allow_failure=True
    )
    branch = (
        branch_result.stdout.decode().strip() if not branch_result.returncode else None
    )
    if topic is None and branch and branch != "main":
        topic = branch
    if topic is not None:
        if not isinstance(topic, str) or topic.startswith("-"):
            raise StatusError("Topic must name a local branch")
        if topic.startswith("refs/heads/"):
            topic = topic[11:]
        if "refs/heads/" + topic not in refs:
            raise StatusError("Topic must name an available local branch")
    cached = {
        name[len("refs/remotes/" + remote + "/") :]: item["sha"]
        for name, item in refs.items()
        if name.startswith("refs/remotes/" + remote + "/")
        and not item["symbolic_target"]
    }
    live = None
    live_state = "not_requested"
    if live_remote:
        try:
            live = _live_heads(git, remote)
            live_state = "queried"
        except StatusError as error:
            live_state = "unavailable"
            issues.append({"scope": "live_remote", "message": str(error)})
    selected = live if live is not None else cached
    summaries = {}
    for name in dict.fromkeys(["main", topic]):
        if name is None:
            continue
        local = refs.get("refs/heads/" + name, {})
        summaries[name] = {
            "local_sha": local.get("sha"),
            "upstream": local.get("upstream"),
            "cached_remote_sha": cached.get(name),
            "live_remote_sha": None if live is None else live.get(name),
            "comparison_basis": "live"
            if live is not None
            else "cached_remote_tracking",
            "comparison": _comparison(git, local.get("sha"), selected.get(name)),
            "role": _role(
                roles, "branches", name, local.get("sha"), local.get("object_sha")
            ),
        }
    status_cache = {}
    status_cache[str(root.resolve())] = _dirty(git, bare)
    worktrees = _worktrees(git)
    for worktree in worktrees:
        key = str(Path(worktree["path"]).resolve())
        if key == str(root.resolve()):
            worktree["status"] = status_cache[key]
        elif all_worktrees:
            try:
                status_cache[key] = _dirty(
                    Git(worktree["path"], timeout), bool(worktree.get("bare"))
                )
                worktree["status"] = status_cache[key]
            except StatusError as error:
                worktree["status"] = {"checked": False, "reason": str(error)}
                issues.append({"scope": "worktree", "message": str(error)})
        else:
            worktree["status"] = {"checked": False, "reason": "Use --all-worktrees"}
    local_branches = [
        dict(
            name=name[11:],
            **item,
            role=_role(roles, "branches", name[11:], item["sha"], item["object_sha"]),
        )
        for name, item in sorted(refs.items())
        if name.startswith("refs/heads/")
    ]
    tags = [
        dict(
            name=name[10:],
            **item,
            role=_role(
                roles,
                "tags",
                name[10:],
                item["sha"] if item["tag_peeling_attempted"] else None,
                item["object_sha"],
            ),
        )
        for name, item in sorted(refs.items())
        if name.startswith("refs/tags/")
    ]
    runtime = _runtime(project, timeout, issues, status_cache)
    for worktree in worktrees:
        key = str(Path(worktree["path"]).resolve())
        if key in status_cache:
            worktree["status"] = status_cache[key]
    return {
        "schema_version": 1,
        "kind": "salam_read_only_git_status",
        "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "state": "partial" if issues else "observed",
        "repository": {
            "path": str(root),
            "head": head,
            "branch": branch,
            "detached": head is not None and branch is None,
            "bare": bare,
            "partial_clone": git.partial_clone(),
            "shallow": git.shallow(),
            "worktree": status_cache[str(root.resolve())],
        },
        "topic": topic,
        "workspace_project": str(project),
        "remote": {
            "name": remote,
            "cached_heads": cached,
            "live_state": live_state,
            "live_heads": live,
            "cached_matches_live": None if live is None else cached == live,
            "note": "No fetch performed. Cached refs may be stale.",
        },
        "selected_branches": summaries,
        "local_branches": local_branches,
        "tags": tags,
        "worktrees": worktrees,
        "role_mapping": {key: roles.get(key) for key in ("state", "path")},
        "runtime": runtime,
        "issues": issues,
        "limitations": [
            "No refs, configuration, index, worktree files or evidence are written.",
            "Role labels do not establish authorship or fresh test qualification.",
            "Ignored results and submodule contents are outside dirty counts.",
            "A Git commit is not a simulator binary identity.",
            "Partial/promisor repositories use refs-only inspection to avoid lazy fetching on older Git.",
        ],
    }


def format_human(report):
    """Render the same observations without adding unverified conclusions."""
    repository = report["repository"]
    dirty = repository["worktree"]
    lines = [
        "SALAM Git status ({})".format(report["state"]),
        "Repository: " + repr(repository["path"]),
        "Checkout: {} @ {}".format(
            repository["branch"] or ("detached" if repository["head"] else "unborn"),
            repository["head"] or "no commit",
        ),
    ]
    if dirty.get("checked"):
        lines.append(
            "Worktree: {} staged, {} unstaged, {} untracked entries, {} conflicts".format(
                dirty["staged"],
                dirty["unstaged"],
                dirty["untracked_entries"],
                dirty["conflicts"],
            )
        )
    if not dirty.get("checked"):
        lines.append(
            "Worktree: not checked (" + dirty.get("reason", "unavailable") + ")"
        )
    if repository.get("partial_clone"):
        lines.append("Partial clone: object traversal/content checks are deferred.")
    if repository.get("shallow"):
        lines.append("Shallow history: unequal-SHA ancestry is incomplete.")
    lines.append(
        "Remote {}: {}; cached refs may be stale; no fetch".format(
            report["remote"]["name"], report["remote"]["live_state"]
        )
    )
    for name, branch in report["selected_branches"].items():
        comparison = branch["comparison"]
        lines.append(
            "{}: {} (ahead {}, behind {}; {})".format(
                name,
                comparison["state"],
                comparison["ahead_by"],
                comparison["behind_by"],
                branch["comparison_basis"],
            )
        )
        if branch["role"]:
            lines.append("  Role: " + str(branch["role"]["role"]))
    saved = []
    for item in report["local_branches"] + report["tags"]:
        role = item["role"]
        if role and item["name"] not in report["selected_branches"]:
            drift = (
                role["expected_sha_matches"] is False
                or role["expected_object_sha_matches"] is False
            )
            saved.append(
                "{}: {} @ {}{}".format(
                    item["name"],
                    role["role"],
                    item["sha"],
                    " (expected identity differs)" if drift else "",
                )
            )
    if saved:
        lines.append("Curated saved refs:")
        lines.extend("  " + line for line in saved)
    for worktree in report["worktrees"]:
        if Path(worktree["path"]) == Path(repository["path"]):
            continue
        status = worktree["status"]
        lines.append(
            "Other worktree {}: {}".format(
                repr(worktree["path"]),
                "{} changed entries".format(status["dirty_entries"])
                if status.get("checked")
                else "not checked",
            )
        )
    runtime = report["runtime"]
    lines.append("Runtime: " + runtime["state"])
    if runtime.get("engine_path"):
        lines.append("  Engine: " + repr(runtime["engine_path"]))
        source = runtime.get("source_git", {})
        lines.append("  Source HEAD: " + str(source.get("head", "unavailable")))
    if runtime.get("binary"):

        lines.append("  Build receipt state: " + str(runtime["build_receipt"]["state"]))
        lines.append(
            "  Recorded compiled-source SHA-256: "
            + str(runtime["build_receipt"]["recorded_compiled_source_sha256"])
        )
        lines.append(
            "  Binary present: {}; size matches record: {}".format(
                runtime["binary"]["exists"], runtime["binary"]["size_matches"]
            )
        )
        lines.append(
            "  Recorded binary SHA-256: " + runtime["binary"]["recorded_sha256"]
        )
        lines.append("  Binary hash and compiled sources were NOT verified.")
    for issue in report["issues"]:
        lines.append("Unavailable [{}]: {}".format(issue["scope"], issue["message"]))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--topic")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--all-worktrees", action="store_true")
    parser.add_argument("--live-remote", action="store_true")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--format", choices=("human", "json"), default="human")
    args = parser.parse_args(argv)
    try:
        report = inspect_status(
            args.repo,
            args.project,
            args.topic,
            args.remote,
            args.all_worktrees,
            args.live_remote,
            args.timeout,
        )
    except (StatusError, OSError, ValueError):
        # Failures must not echo subprocess stderr, URLs, or malformed file data.
        report = {
            "schema_version": 1,
            "state": "unavailable",
            "message": "Status could not be collected safely",
        }
        print(json.dumps(report) if args.format == "json" else report["message"])
        return 1
    print(
        json.dumps(report, indent=2) if args.format == "json" else format_human(report),
        end="\n" if args.format == "json" else "",
    )
    return 0 if report["state"] == "observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
