# SPDX-License-Identifier: BSD-3-Clause
"""Exercise the real CLI transport and guarded ruleset flow against fake gh."""
import base64
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "git_policy_under_test", ROOT / "workbench/scripts/manage_git_policy.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
MAIN = "a" * 40


class FakeGh:
    def __init__(self, raw):
        self.raw = raw
        self.remote_raw = raw
        self.refs = dict(MODULE.PINNED_REFS, **{"refs/heads/main": MAIN})
        self.repository = {
            "full_name": MODULE.REPOSITORY,
            "id": MODULE.REPOSITORY_ID,
            "default_branch": "main",
            "permissions": {"admin": True},
        }
        self.checks = [
            {
                "id": index,
                "name": name,
                "head_sha": MAIN,
                "status": "completed",
                "conclusion": "success",
                "app": {"id": MODULE.ACTIONS_ID, "slug": "github-actions"},
            }
            for index, name in enumerate(MODULE.CHECKS, 1)
        ]
        self.rulesets = {}
        self.calls = []
        self.classic = None
        self.admin_status = None
        self.fail_post = None
        self.move_main_on_read = None
        self.main_reads = 0
        self.corrupt_after_post = False

    def __call__(self, argv, **kwargs):
        method = argv[argv.index("--method") + 1]
        endpoint = next(a for a in argv if a.startswith(MODULE.API_ROOT))
        self.calls.append((method, endpoint, copy.deepcopy(kwargs)))
        try:
            value = self.route(method, endpoint, kwargs)
        except MODULE.GitHubError as error:
            return subprocess.CompletedProcess(
                argv, 1, "", "fixture secret must not leak (HTTP %d)" % error.status
            )
        return subprocess.CompletedProcess(argv, 0, json.dumps(value), "")

    def fail(self, method, endpoint, status=404):
        raise MODULE.GitHubError(method, endpoint, status)

    def route(self, method, endpoint, kwargs):
        path, query = endpoint.split("?", 1) if "?" in endpoint else (endpoint, "")
        suffix = path[len(MODULE.API_ROOT) :]
        if method == "POST":
            assert suffix == "/rulesets"
            count = sum(row[0] == "POST" for row in self.calls)
            if self.fail_post == count:
                self.fail(method, endpoint, 403)
            body = json.loads(kwargs["input"])
            identity = len(self.rulesets) + 10
            self.rulesets[identity] = dict(body, id=identity, source_type="Repository")
            if self.corrupt_after_post:
                self.refs[next(iter(MODULE.PINNED_REFS))] = "b" * 40
            return self.rulesets[identity]
        assert method == "GET"
        if not suffix:
            return self.repository
        if suffix.startswith("/git/ref/"):
            ref = "refs/" + unquote(suffix[len("/git/ref/") :])
            if ref == "refs/heads/main":
                self.main_reads += 1
                if self.main_reads == self.move_main_on_read:
                    self.refs[ref] = "b" * 40
            return {"ref": ref, "object": {"sha": self.refs[ref]}}
        if suffix.endswith("/protection"):
            if self.admin_status:
                self.fail(method, endpoint, self.admin_status)
            if self.classic is None:
                self.fail(method, endpoint)
            return self.classic
        if suffix.startswith("/contents/"):
            if self.remote_raw is None:
                self.fail(method, endpoint)
            assert parse_qs(query)["ref"] == [self.refs["refs/heads/main"]]
            raw = self.remote_raw
            return {
                "type": "file",
                "encoding": "base64",
                "path": MODULE.POLICY_PATH,
                "content": base64.b64encode(raw).decode(),
                "sha": hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\0" + raw
                ).hexdigest(),
            }
        if suffix.endswith("/check-runs"):
            page = int(parse_qs(query)["page"][0])
            start = (page - 1) * 100
            return {
                "total_count": len(self.checks),
                "check_runs": self.checks[start : start + 100],
            }
        if suffix == "/rulesets":
            if self.admin_status:
                self.fail(method, endpoint, self.admin_status)
            page = int(parse_qs(query)["page"][0])
            rows = [
                {
                    "id": identity,
                    "name": value["name"],
                    "source_type": value["source_type"],
                }
                for identity, value in self.rulesets.items()
            ]
            return rows[(page - 1) * 100 : page * 100]
        if suffix.startswith("/rulesets/"):
            return self.rulesets[int(suffix.rsplit("/", 1)[1])]
        raise AssertionError("Unexpected API route: " + endpoint)


class GitPolicyTests(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / MODULE.POLICY_PATH).read_bytes()
        self.policy = MODULE.load_policy(self.raw)
        self.fake = FakeGh(self.raw)
        self.api = MODULE.GitHub(
            executable="C:/Program Files/GitHub CLI/gh.exe", runner=self.fake
        )

    def inspect(self, expected=MAIN):
        return MODULE.inspect_policy(self.api, self.policy, self.raw, expected)

    def apply(self, expected=MAIN):
        return MODULE.apply_policy(self.api, self.policy, self.raw, expected)

    def assert_no_writes(self):
        self.assertTrue(all(row[0] == "GET" for row in self.fake.calls))

    def test_policy_has_solo_owner_pr_and_exact_checkpoint_object_rules(self):
        rules = MODULE._rules(self.policy["rulesets"][0]["rules"])
        self.assertEqual(rules["pull_request"]["required_approving_review_count"], 0)
        self.assertFalse(rules["pull_request"]["require_last_push_approval"])
        self.assertNotIn("update", rules)
        self.assertNotIn("required_linear_history", rules)
        self.assertEqual(len(self.policy["pinned_refs"]), 5)
        for body in self.policy["rulesets"][1:]:
            self.assertEqual(
                MODULE._rules(body["rules"])["update"],
                {"update_allows_fetch_and_merge": False},
            )

    def test_default_plan_is_get_only_even_when_ready_and_path_contains_spaces(self):
        result = self.inspect()
        self.assertTrue(result["apply_ready"])
        self.assertEqual(len(result["actions"]), 3)
        self.assert_no_writes()
        argv_kwargs = self.fake.calls[0][2]
        self.assertNotIn("shell", argv_kwargs)
        self.assertIsNone(argv_kwargs["input"])

    def test_unmerged_policy_and_new_missing_check_are_honest_plan_blockers(self):
        self.fake.remote_raw = None
        self.fake.checks.pop()
        result = self.inspect()
        self.assertEqual(result["state"], "planned")
        self.assertFalse(result["apply_ready"])
        self.assertTrue(any("remote main" in b for b in result["blockers"]))
        self.assertFalse(result["checks"]["Repository hygiene"]["green_trusted_check"])
        self.assertEqual(self.apply()["state"], "blocked")
        self.assert_no_writes()

    def test_remote_policy_must_match_exact_bytes_not_only_json_meaning(self):
        self.fake.remote_raw = self.raw + b"\n"
        self.assertFalse(self.inspect()["apply_ready"])
        self.assertEqual(self.apply()["state"], "blocked")
        self.assert_no_writes()

    def test_apply_requires_full_matching_reviewed_main(self):
        for value in (None, "b" * 40):
            self.assertEqual(self.apply(value)["state"], "blocked")
        with self.assertRaisesRegex(ValueError, "full lowercase"):
            self.inspect("a" * 7)
        self.assert_no_writes()

    def test_wrong_repository_id_or_owner_fails_before_any_admin_request(self):
        for field, value in (("full_name", "gem5/gem5"), ("id", 1)):
            with self.subTest(field=field):
                fake = FakeGh(self.raw)
                fake.repository[field] = value
                api = MODULE.GitHub(runner=fake)
                with self.assertRaisesRegex(ValueError, "identity"):
                    MODULE.inspect_policy(api, self.policy, self.raw, MAIN)
                self.assertEqual(len(fake.calls), 1)

    def test_tag_object_movement_blocks_even_if_peeled_commit_could_match(self):
        ref = "refs/tags/gem5-26-checkpoint-20261105"
        self.fake.refs[ref] = "b" * 40
        self.assertFalse(self.inspect()["apply_ready"])
        self.assertEqual(self.apply()["state"], "blocked")
        self.assert_no_writes()

    def test_old_wrong_app_neutral_pending_or_ambiguous_checks_do_not_qualify(self):
        changes = [
            {"head_sha": "b" * 40},
            {"conclusion": "neutral"},
            {"status": "in_progress"},
            {"conclusion": "skipped"},
            {"app": {"id": 1, "slug": "github-actions"}},
            {"app": {"id": MODULE.ACTIONS_ID, "slug": "other-app"}},
        ]
        for change in changes:
            with self.subTest(change=change):
                self.fake = FakeGh(self.raw)
                self.fake.checks[0].update(change)
                self.api = MODULE.GitHub(runner=self.fake)
                self.assertFalse(self.inspect()["apply_ready"])
                self.assertEqual(self.apply()["state"], "blocked")
                self.assert_no_writes()
        self.fake = FakeGh(self.raw)
        self.fake.checks.append(copy.deepcopy(self.fake.checks[0]))
        self.api = MODULE.GitHub(runner=self.fake)
        self.assertFalse(self.inspect()["apply_ready"])

    def test_check_pagination_cannot_hide_required_jobs_on_second_page(self):
        self.fake.checks = [
            dict(self.fake.checks[0], id=1000 + i, name="unrelated-%d" % i)
            for i in range(100)
        ] + self.fake.checks
        self.assertTrue(self.inspect()["apply_ready"])
        self.assertTrue(any("page=2" in row[1] for row in self.fake.calls))

    def test_permission_failure_remains_unknown_and_stderr_is_not_leaked(self):
        self.fake.admin_status = 403
        result = self.inspect()
        self.assertEqual(result["administration_read"], "unknown")
        self.assertEqual(result["administration_write"], "not_tested")
        self.assertFalse(result["apply_ready"])
        self.assertNotIn("secret", json.dumps(result))
        self.assert_no_writes()

    def test_classic_or_unknown_rulesets_are_never_overwritten(self):
        self.fake.classic = {"enforce_admins": {"enabled": True}}
        self.assertEqual(self.apply()["state"], "blocked")
        self.assert_no_writes()
        self.fake.classic = None
        self.fake.rulesets[1] = {"name": "some other rule", "source_type": "Repository"}
        self.assertEqual(self.apply()["state"], "blocked")
        self.assert_no_writes()

    def test_different_existing_named_rule_is_not_updated_or_deleted(self):
        body = copy.deepcopy(self.policy["rulesets"][0])
        body.update(id=20, source_type="Repository", bypass_actors=[{"actor_id": 5}])
        self.fake.rulesets[20] = body
        self.assertEqual(self.apply()["state"], "blocked")
        self.assert_no_writes()

    def test_main_moving_after_preflight_blocks_first_write(self):
        self.fake.move_main_on_read = 2
        self.assertEqual(self.apply()["state"], "blocked")
        self.assert_no_writes()

    def test_apply_creates_only_missing_rules_and_second_apply_is_idempotent(self):
        before_refs = dict(self.fake.refs)
        result = self.apply()
        self.assertEqual(result["state"], "applied")
        self.assertEqual(len(result["created_rulesets"]), 3)
        posts = [row for row in self.fake.calls if row[0] == "POST"]
        self.assertEqual(len(posts), 3)
        self.assertTrue(all(row[1] == MODULE.API_ROOT + "/rulesets" for row in posts))
        count = len(self.fake.calls)
        second = self.apply()
        self.assertEqual(second["created_rulesets"], [])
        self.assertTrue(all(row[0] == "GET" for row in self.fake.calls[count:]))
        self.assertEqual(self.fake.refs, before_refs)

    def test_failure_after_one_creation_preserves_partial_state_without_rollback(self):
        self.fake.fail_post = 2
        result = self.apply()
        self.assertEqual(result["state"], "failed_partial")
        self.assertEqual(len(result["created_rulesets"]), 1)
        self.assertEqual(len(self.fake.rulesets), 1)
        self.assertTrue(all(row[0] in ("GET", "POST") for row in self.fake.calls))

    def test_pin_drift_after_first_creation_stops_remaining_creations(self):
        self.fake.corrupt_after_post = True
        result = self.apply()
        self.assertEqual(result["state"], "failed_partial")
        self.assertEqual(len(self.fake.rulesets), 1)

    def test_policy_rejects_bypasses_changed_pins_boolean_approval_and_foreign_repo(
        self,
    ):
        for mutate in (
            lambda p: p.update(repository="gem5/gem5"),
            lambda p: p["pinned_refs"].update(
                {next(iter(MODULE.PINNED_REFS)): "b" * 40}
            ),
            lambda p: p["rulesets"][0].update(bypass_actors=[{"actor_id": 5}]),
            lambda p: p["rulesets"][0]["rules"][2]["parameters"].update(
                required_approving_review_count=False
            ),
        ):
            policy = json.loads(self.raw)
            mutate(policy)
            with self.assertRaises(ValueError):
                MODULE.load_policy(json.dumps(policy).encode())
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            MODULE.load_policy(
                self.raw.replace(
                    b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1'
                )
            )

    def test_transport_never_accepts_other_repo_or_destructive_method(self):
        for method, endpoint in (
            ("DELETE", MODULE.API_ROOT + "/rulesets/1"),
            ("PUT", MODULE.API_ROOT + "/git/refs/heads/main"),
            ("POST", "repos/gem5/gem5/rulesets"),
            ("POST", MODULE.API_ROOT + "/git/refs/heads/main"),
        ):
            with self.assertRaises(ValueError):
                self.api.request(method, endpoint, {})
        self.assertEqual(self.fake.calls, [])

    def test_cli_defaults_to_plan_and_uses_explicit_gh_executable(self):
        buffer = io.StringIO()
        with patch.object(MODULE, "GitHub", return_value=self.api) as constructor:
            with contextlib.redirect_stdout(buffer):
                code = MODULE.main(["--expected-main", MAIN, "--gh", "fixture gh path"])
        self.assertEqual(code, 0)
        constructor.assert_called_once_with("fixture gh path")
        self.assertEqual(json.loads(buffer.getvalue())["state"], "planned")
        self.assert_no_writes()

    def test_in_memory_body_cannot_diverge_from_reviewed_remote_policy_bytes(self):
        self.policy["rulesets"][0]["bypass_actors"] = [{"actor_id": 5}]
        with self.assertRaisesRegex(ValueError, "reviewed bytes"):
            self.inspect()
        self.assertEqual(self.fake.calls, [])

    def test_first_post_failure_reports_attempt_without_claiming_no_mutation(self):
        self.fake.fail_post = 1
        result = self.apply()
        self.assertEqual(result["state"], "failed_partial")
        self.assertEqual(result["created_rulesets"], [])
        self.assertEqual(result["attempted_creates"], [MODULE.NAMES[0]])
        self.assertEqual(self.fake.rulesets, {})

    def test_server_neutral_defaults_and_order_are_equivalent_without_overwrite(self):
        body = copy.deepcopy(self.policy["rulesets"][0])
        params = body["rules"][2]["parameters"]
        params.update(
            allowed_merge_methods=["merge", "squash", "rebase"],
            required_reviewers=[],
            require_extra_approval_for_unattributed_changes=True,
            dismissal_restriction={"enabled": False, "allowed_actors": []},
        )
        body["rules"][3]["parameters"]["required_status_checks"].reverse()
        body.update(id=20, source_type="Repository")
        self.fake.rulesets[20] = body
        result = self.inspect()
        self.assertTrue(result["apply_ready"])
        self.assertTrue(result["installed_rulesets"][MODULE.NAMES[0]]["matches"])
        self.assertEqual(len(result["actions"]), 2)
        self.assert_no_writes()

    def test_unknown_server_rule_parameter_is_not_silently_accepted(self):
        body = copy.deepcopy(self.policy["rulesets"][0])
        body["rules"][2]["parameters"]["unknown_future_permission"] = True
        body.update(id=20, source_type="Repository")
        self.fake.rulesets[20] = body
        self.assertFalse(self.inspect()["apply_ready"])
        self.assertEqual(self.apply()["state"], "blocked")
        self.assert_no_writes()

    def test_ref_drift_during_last_prewrite_listing_blocks_first_post(self):
        original = self.fake.route
        listings = [0]

        def drift(method, endpoint, kwargs):
            value = original(method, endpoint, kwargs)
            if method == "GET" and "/rulesets?" in endpoint:
                listings[0] += 1
                if listings[0] == 2:
                    self.fake.refs["refs/heads/main"] = "b" * 40
            return value

        self.fake.route = drift
        result = self.apply()
        self.assertEqual(result["state"], "blocked")
        self.assertIn("write boundary", result["error"])
        self.assert_no_writes()

    def test_late_final_ref_drift_cannot_be_reported_as_success(self):
        original = self.fake.route

        def drift(method, endpoint, kwargs):
            value = original(method, endpoint, kwargs)
            if (
                method == "GET"
                and "/rulesets?" in endpoint
                and len(self.fake.rulesets) == 3
            ):
                self.fake.refs[next(iter(MODULE.PINNED_REFS))] = "b" * 40
            return value

        self.fake.route = drift
        result = self.apply()
        self.assertEqual(result["state"], "failed_partial")
        self.assertEqual(len(result["created_rulesets"]), 3)
        self.assertIn("write boundary", result["error"])

    def test_interrupt_after_post_preserves_uncertain_remote_outcome(self):
        original = self.fake.route

        def interrupt(method, endpoint, kwargs):
            value = original(method, endpoint, kwargs)
            if method == "POST":
                raise KeyboardInterrupt()
            return value

        self.fake.route = interrupt
        result = self.apply()
        self.assertEqual(result["state"], "failed_partial")
        self.assertEqual(result["created_rulesets"], [])
        self.assertEqual(result["attempted_creates"], [MODULE.NAMES[0]])
        self.assertEqual(len(self.fake.rulesets), 1)
        self.assertIn("KeyboardInterrupt", result["error"])


if __name__ == "__main__":
    unittest.main()
