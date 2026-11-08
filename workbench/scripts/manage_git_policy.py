#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Plan fork rulesets; apply only a policy already reviewed onto remote main.

Default execution performs GET requests only. No refs, tags, existing rulesets,
or classic protection are modified. Apply can create missing rulesets; partial
failure preserves those rules and reports them rather than weakening protection.
Immediate ref rechecks narrow races; GitHub offers no atomic transaction across
these independent reads and ruleset creation requests.
"""
import argparse
import base64
import copy
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

REPOSITORY = "Josh-Slycord/gem5-SALAM-dev"
REPOSITORY_ID = 536408321
POLICY_PATH = ".github/salam-git-policy.json"
API_ROOT = "repos/" + REPOSITORY
CHECKS = (
    "Python contracts and SALAM source generation",
    "Python 3.12 contracts and explicit gem5 26 source generation",
    "PowerShell syntax and packaging failure controls",
    "Repository hygiene",
)
ACTIONS_ID = 15368
PINNED_REFS = {
    "refs/heads/legacy/gem5-21.1-workbench-20261107": "48fe84fa2f1c52e95fbc2382d62f26013fa78cd7",
    "refs/heads/codex/simobject-lifecycle-20261107": "81cb2734f0faa96d24dde4a970c8dc82a77ff38d",
    "refs/heads/codex/track-ab-integration-20261106": "1f4e6225dc04d305bdf2a2be424fab029d471d4e",
    "refs/tags/gem5-26-checkpoint-20261105": "38c99ba353116039cd72e2d3c225304f93a3ce44",
    "refs/tags/gem5-26-integration-checkpoint-20261105": "43cb531d14a46bb5694cbc601e0241fa3295b836",
}
NAMES = ("SALAM main", "SALAM frozen branches", "SALAM frozen tags")
SHA = re.compile(r"^[0-9a-f]{40}$")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field: " + key)
        result[key] = value
    return result


def _rules(rows):
    result = {}
    for row in rows:
        if set(row) - {"type", "parameters"}:
            raise ValueError("Unexpected rule fields")
        name = row["type"]
        if name in result:
            raise ValueError("Duplicate ruleset rule: " + name)
        result[name] = row.get("parameters", {})
    return result


def load_policy(raw):
    policy = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    if not isinstance(policy, dict) or set(policy) != {
        "schema_version",
        "repository",
        "repository_id",
        "pinned_refs",
        "rulesets",
    }:
        raise ValueError("Unsupported policy fields")
    if (
        type(policy["schema_version"]) is not int
        or policy["schema_version"] != 1
        or policy["repository"] != REPOSITORY
        or type(policy["repository_id"]) is not int
        or policy["repository_id"] != REPOSITORY_ID
        or policy["pinned_refs"] != PINNED_REFS
    ):
        raise ValueError("Policy must target the exact fork and preserved ref objects")
    bodies = policy["rulesets"]
    if not isinstance(bodies, list) or len(bodies) != 3:
        raise ValueError("Exactly three reviewed rulesets are required")
    indexed = {body["name"]: body for body in bodies}
    if set(indexed) != set(NAMES) or len(indexed) != len(bodies):
        raise ValueError("Unexpected or duplicate ruleset name")
    for name, body in indexed.items():
        if set(body) != {
            "name",
            "target",
            "enforcement",
            "bypass_actors",
            "conditions",
            "rules",
        }:
            raise ValueError("Unexpected ruleset fields")
        tag = name == NAMES[2]
        include = (
            ["refs/heads/main"]
            if name == NAMES[0]
            else sorted(ref for ref in PINNED_REFS if ("/tags/" in ref) == tag)
        )
        if (
            body["target"] != ("tag" if tag else "branch")
            or body["enforcement"] != "active"
            or body["bypass_actors"] != []
            or body["conditions"] != {"ref_name": {"include": include, "exclude": []}}
        ):
            raise ValueError("Ruleset targets, enforcement, or bypasses differ")
        expected = {"deletion": {}, "non_fast_forward": {}}
        if name == NAMES[0]:
            expected.update(
                pull_request={
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 0,
                    "required_review_thread_resolution": True,
                },
                required_status_checks={
                    "do_not_enforce_on_create": False,
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [
                        {"context": context, "integration_id": ACTIONS_ID}
                        for context in CHECKS
                    ],
                },
            )
        else:
            expected["update"] = {"update_allows_fetch_and_merge": False}
        if canonical(_rules(body["rules"])) != canonical(expected):
            raise ValueError("Rules differ from the reviewed solo-owner policy")
    return policy


class GitHubError(RuntimeError):
    def __init__(self, method, endpoint, status=None):
        self.status = status
        suffix = "HTTP " + str(status) if status else "transport or authentication"
        super().__init__("GitHub API " + method + " " + endpoint + " failed: " + suffix)


class GitHub:
    def __init__(self, executable=None, runner=subprocess.run):
        self.executable = executable or shutil.which("gh") or "gh"
        self.runner = runner

    def request(self, method, endpoint, body=None):
        if method not in ("GET", "POST") or not (
            endpoint == API_ROOT or endpoint.startswith(API_ROOT + "/")
        ):
            raise ValueError("Only this fork's GET/create requests are supported")
        if method == "POST" and endpoint != API_ROOT + "/rulesets":
            raise ValueError("Only missing rulesets may be created")
        argv = [
            self.executable,
            "api",
            "--hostname",
            "github.com",
            "--method",
            method,
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            "X-GitHub-Api-Version: 2026-03-10",
            endpoint,
        ]
        if body is not None:
            argv.extend(("--input", "-"))
        try:
            done = self.runner(
                argv,
                input=canonical(body) if body is not None else None,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise GitHubError(method, endpoint) from error
        if done.returncode:
            match = re.search(r"HTTP\s+([0-9]{3})", done.stderr or "")
            raise GitHubError(method, endpoint, int(match[1]) if match else None)
        try:
            return json.loads(done.stdout, object_pairs_hook=_unique)
        except (ValueError, TypeError) as error:
            raise GitHubError(method, endpoint) from error


def _paged(api, endpoint, key=None):
    collected = []
    for page in range(1, 101):
        separator = "&" if "?" in endpoint else "?"
        data = api.request(
            "GET", endpoint + separator + "per_page=100&page=" + str(page)
        )
        rows = data if key is None else data[key]
        if not isinstance(rows, list):
            raise ValueError("Unexpected API pagination response")
        collected.extend(rows)
        if len(rows) < 100:
            if key is not None and len(collected) != data["total_count"]:
                raise ValueError("Incomplete check-run pagination")
            return collected
    raise ValueError("API pagination limit exceeded")


def _ref(api, ref):
    data = api.request("GET", API_ROOT + "/git/ref/" + quote(ref[5:], safe="/"))
    if data.get("ref") != ref or not SHA.fullmatch(data["object"]["sha"]):
        raise ValueError("Unexpected remote ref response")
    return data["object"]["sha"]


def _body(data):
    body = {
        key: copy.deepcopy(data[key])
        for key in (
            "name",
            "target",
            "enforcement",
            "bypass_actors",
            "conditions",
            "rules",
        )
    }
    body["rules"] = _rules(body["rules"])
    # GitHub may include these documented defaults even when omitted on create.
    # Only their exact neutral values are equivalent; unknown fields still block.
    params = body["rules"].get("pull_request", {})
    defaults = {
        "allowed_merge_methods": ["merge", "squash", "rebase"],
        "required_reviewers": [],
        "require_extra_approval_for_unattributed_changes": True,
        "dismissal_restriction": {"allowed_actors": [], "enabled": False},
    }
    for key, value in defaults.items():
        if key in params and canonical(params[key]) == canonical(value):
            del params[key]
    for key in ("include", "exclude"):
        body["conditions"]["ref_name"][key].sort()
    checks = (
        body["rules"].get("required_status_checks", {}).get("required_status_checks")
    )
    if checks is not None:
        checks.sort(key=canonical)
    return body


def inspect_policy(api, policy, raw, expected_main=None):
    if expected_main is not None and not SHA.fullmatch(expected_main):
        raise ValueError("--expected-main must be a full lowercase 40-character SHA")
    if canonical(policy) != canonical(load_policy(raw)):
        raise ValueError("Applied policy body differs from its reviewed bytes")
    repository = api.request("GET", API_ROOT)
    if repository["full_name"] != REPOSITORY or repository["id"] != REPOSITORY_ID:
        raise ValueError("Remote repository identity differs from the allowed fork")
    if repository.get("default_branch") != "main":
        raise ValueError("The fork's default branch is no longer main")
    blockers = []
    main = _ref(api, "refs/heads/main")
    if expected_main is None:
        blockers.append("--expected-main is required before apply")
    elif main != expected_main:
        blockers.append("Remote main differs from --expected-main")
    refs = {ref: _ref(api, ref) for ref in PINNED_REFS}
    if refs != PINNED_REFS:
        blockers.append("A preserved branch or tag object differs from its pinned SHA")
    admin = repository.get("permissions", {}).get("admin") is True
    if not admin:
        blockers.append("Repository administrator permission is unknown or absent")
    read_permission = "confirmed"
    classic = {}
    for ref in ["refs/heads/main"] + [r for r in PINNED_REFS if "/heads/" in r]:
        endpoint = API_ROOT + "/branches/" + quote(ref[11:], safe="") + "/protection"
        try:
            classic[ref] = api.request("GET", endpoint)
            blockers.append("Existing classic branch protection requires manual review")
        except GitHubError as error:
            if error.status == 404 and admin:
                classic[ref] = None
            else:
                classic[ref] = "unknown"
                read_permission = "unknown"
                blockers.append(str(error))
    remote_policy = None
    try:
        data = api.request(
            "GET", API_ROOT + "/contents/" + POLICY_PATH + "?ref=" + main
        )
        content = base64.b64decode(data["content"].replace("\n", ""), validate=True)
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if (
            data.get("type") != "file"
            or data.get("encoding") != "base64"
            or data.get("path") != POLICY_PATH
            or data.get("sha") != blob
            or content != raw
        ):
            blockers.append("Local policy bytes are not identical to remote main")
        else:
            remote_policy = data["sha"]
    except GitHubError as error:
        blockers.append("Reviewed policy is unavailable on remote main: " + str(error))
    checks = _paged(
        api, API_ROOT + "/commits/" + main + "/check-runs?filter=latest", "check_runs"
    )
    observed = {}
    for name in CHECKS:
        matches = [check for check in checks if check.get("name") == name]
        valid = len(matches) == 1 and (
            matches[0].get("head_sha") == main
            and matches[0].get("status") == "completed"
            and matches[0].get("conclusion") == "success"
            and matches[0].get("app", {}).get("id") == ACTIONS_ID
            and matches[0].get("app", {}).get("slug") == "github-actions"
        )
        observed[name] = {
            "green_trusted_check": valid,
            "check_ids": [c["id"] for c in matches],
        }
        if not valid:
            blockers.append("Missing unique successful Actions check on main: " + name)
    desired = {body["name"]: body for body in policy["rulesets"]}
    installed = {}
    try:
        for row in _paged(api, API_ROOT + "/rulesets"):
            if row.get("name") not in desired or row.get("source_type") != "Repository":
                blockers.append("Unknown or inherited ruleset requires manual review")
                continue
            name = row["name"]
            if name in installed:
                blockers.append("Duplicate named ruleset requires manual review")
                continue
            data = api.request("GET", API_ROOT + "/rulesets/" + str(row["id"]))
            installed[name] = {
                "id": row["id"],
                "matches": canonical(_body(data)) == canonical(_body(desired[name])),
            }
            if not installed[name]["matches"]:
                blockers.append(
                    "Existing ruleset differs; it will not be overwritten: " + name
                )
    except GitHubError as error:
        read_permission = "unknown"
        blockers.append(str(error))
    actions = [
        {"method": "POST", "endpoint": API_ROOT + "/rulesets", "body": body}
        for name, body in desired.items()
        if name not in installed
    ]
    return {
        "state": "planned",
        "applied": False,
        "apply_ready": not blockers,
        "repository": REPOSITORY,
        "repository_id": REPOSITORY_ID,
        "expected_main": expected_main,
        "observed_main": main,
        "policy_sha256": hashlib.sha256(raw).hexdigest(),
        "remote_policy_blob": remote_policy,
        "repository_admin": admin,
        "administration_read": read_permission,
        "administration_write": "not_tested",
        "pinned_ref_objects": refs,
        "checks": observed,
        "installed_rulesets": installed,
        "blockers": blockers,
        "actions": actions,
    }


def _assert_current_refs(api, expected_main):
    # Read main last, immediately before the write/return boundary.
    refs = {ref: _ref(api, ref) for ref in PINNED_REFS}
    main = _ref(api, "refs/heads/main")
    if refs != PINNED_REFS or main != expected_main:
        raise ValueError("Remote main or preserved ref changed at the write boundary")


def apply_policy(api, policy, raw, expected_main):
    report = inspect_policy(api, policy, raw, expected_main)
    created = []
    attempted = []
    try:
        if not report["apply_ready"]:
            raise ValueError("Apply blocked: " + "; ".join(report["blockers"]))
        for action in report["actions"]:
            fresh = inspect_policy(api, policy, raw, expected_main)
            if not fresh["apply_ready"]:
                raise ValueError(
                    "Pre-write guards changed: " + "; ".join(fresh["blockers"])
                )
            if action["body"]["name"] in fresh["installed_rulesets"]:
                continue
            _assert_current_refs(api, expected_main)
            attempted.append(action["body"]["name"])
            response = api.request("POST", action["endpoint"], action["body"])
            created.append({"id": response["id"], "name": action["body"]["name"]})
        final = inspect_policy(api, policy, raw, expected_main)
        if not final["apply_ready"] or final["actions"]:
            raise ValueError("Post-apply verification differs from the reviewed policy")
        _assert_current_refs(api, expected_main)
        final.update(
            state="applied" if created else "already_present",
            applied=bool(created),
            created_rulesets=created,
            attempted_creates=attempted,
            administration_write="confirmed_for_ruleset_creation"
            if created
            else "not_tested",
        )
        return final
    except (ValueError, GitHubError, KeyError, TypeError, KeyboardInterrupt) as error:
        report.update(
            state="failed_partial" if attempted else "blocked",
            applied=False,
            created_rulesets=created,
            attempted_creates=attempted,
            error=type(error).__name__ + ": " + str(error),
            recovery="Existing and newly created rules are preserved; no automatic rollback.",
        )
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy", type=Path, default=Path(__file__).resolve().parents[2] / POLICY_PATH
    )
    parser.add_argument("--expected-main")
    parser.add_argument(
        "--gh", help="Path to the local GitHub CLI executable; no shell is used"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Create only missing reviewed rulesets"
    )
    args = parser.parse_args(argv)
    try:
        raw = args.policy.read_bytes()
        policy = load_policy(raw)
        api = GitHub(args.gh)
        report = (
            apply_policy(api, policy, raw, args.expected_main)
            if args.apply
            else inspect_policy(api, policy, raw, args.expected_main)
        )
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        GitHubError,
        KeyboardInterrupt,
    ) as error:
        report = {"state": "blocked", "applied": False, "error": str(error)}
    print(json.dumps(report, indent=2))
    return 1 if report["state"] in ("blocked", "failed_partial") else 0


if __name__ == "__main__":
    raise SystemExit(main())
