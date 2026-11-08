# Contributing to this SALAM fork

This guide is the working Git policy for `Josh-Slycord/gem5-SALAM-dev`.
Develop topic branches from this fork's current `main` and submit PRs back to
this fork's `main`. The inherited gem5 contribution guide describes upstream
gem5; its `develop` target does not select the integration branch here.
Official gem5 and TeCSAR repositories are reference sources until Josh
explicitly authorizes a separate upstream contribution.

## Working agreement

Use one uniquely named branch and worktree per task, with one integration
owner coordinating merges. Record the repository, branch, full base SHA and
worktree in the task handoff. A prefix such as `gemini/` or `codex/` describes
workflow ownership; it does not establish source authorship.

Read Git state with `git --no-optional-locks -c core.fsmonitor=false ...`.
Inspect status and existing worktrees before changing a checkout. Linked
worktrees share branch refs, configuration and hooks. Do not change shared
configuration, move another task's branch or bypass hooks as routine cleanup.

For a new task, after checking that `origin` is Josh's fork:

```bash
git --no-optional-locks -c core.fsmonitor=false fetch --no-tags origin
git --no-optional-locks -c core.fsmonitor=false worktree add --no-track \
  -b gemini/descriptive-topic /absolute/new/worktree origin/main
```

Use a new, unused path and branch name. Run commands one at a time and inspect
failures. `--no-track` prevents a topic branch from accidentally tracking
`origin/main`. When authorized to publish, push an explicit topic ref and
establish its matching upstream:

```bash
git push --set-upstream origin HEAD:refs/heads/gemini/descriptive-topic
```

Do not push directly to main, force-push, prune, delete branches or discard
files during routine work. Preserve committed heads and separately inventory
and archive dirty, untracked and relevant ignored work before any migration.
A saved branch protects commits, not those other files.

## Review and integration

Keep commits focused. Preserve original authors, notices, immutable import
SHAs and adaptation scope; see [SALAM credits](../../SALAM_CREDITS.md) and
the [source-origin ledger](provenance/SALAM_SOURCE_ORIGINS.json). An agent's
claim, a matching name or `git cherry` output is not proof of complete
semantic integration. Port reviewed changes from old parallel branches
selectively when their implementation has already been repaired on main.

Use the [PR template](../../.github/PULL_REQUEST_TEMPLATE.md). Separate
source-only checks, documentation builds, simulator builds, real numerical
runs, negative controls and visible GUI checks. Report failures and skipped
checks explicitly. A green source workflow is not a simulator qualification.

The integration owner reviews the final diff and source/runtime identities,
waits for required checks on the final head, and merges only when authorized.
Preserve merge ancestry and source attribution. Do not squash or rebase shared
or qualified history to make ahead/behind counts smaller.

## Main and saved versions

[Git roles](git-roles.json) records main, the legacy source, qualification
bookmarks and preserved tag objects. It is an authored role map, not a live
claim that every named local branch is current. The status command combines
it with actual Git observations.

Main is the active gem5 26 integration line. The legacy gem5 21.1.0.1 branch,
Track A/B and lifecycle checkpoints, original binaries and qualification
receipts remain preserved. Merged topic branches may stay behind main:
that is expected for saved bookmarks. Do not move a checkpoint to resolve it.

[`salam-git-policy.json`](../../.github/salam-git-policy.json) contains the
reviewable fork protection policy: main requires a PR and existing source
checks, with no force pushes or deletion; exact saved branches and tags are
frozen separately. Zero required approvals supports the solo maintainer;
it does not authorize an agent to merge without Josh's instruction.
The declared repository-hygiene job can become required only after this PR's
workflow is present on main and all declared checks have run successfully there.
From the workbench directory, inspect a read-only deployment plan:

```bash
python3 -B scripts/manage_git_policy.py --expected-main FULL_CURRENT_MAIN_SHA
```

The local helper uses the existing authenticated `gh` executable. `--gh` can
select an installed executable explicitly. Planning makes read-only API calls;
`--apply` is a separate, explicit administration operation after the PR lands.
Apply checks the exact fork identity, current main, preserved branch/tag OIDs,
reviewed policy bytes on main and successful check names/producing app. It
refuses unexpected or conflicting existing protections and never deletes
rulesets or rewrites refs. Ref checks before and after changes detect drift,
but separate GitHub API operations are not an atomic transaction. Preserve and
inspect any partial-failure report before retrying.

This unmerged PR does not activate live protection. Consult the task's settings
receipt or GitHub before claiming the policy is active.

## Read-only status

From the workbench directory:

```bash
python3 -B -m salam_workbench.git_status
python3 -B -m salam_workbench.git_status --format json
python3 -B -m salam_workbench.git_status --all-worktrees
python3 -B -m salam_workbench.git_status --live-remote
```

`--repo` selects the Git checkout and its role map. `--project` selects the
Workbench directory whose runtime binding is inspected; it does not switch
Git checkouts. Both accept explicit paths, which is useful when inspecting an
existing installation from a separate topic worktree.

The default is offline and labels cached remote-tracking refs. Explicit live
inspection uses `ls-remote`; it does not fetch objects or update refs. If a
live object is unavailable locally, ancestry counts remain unknown. Optional
inspection of all worktrees can take longer on archive folders.

Runtime source HEAD, recorded build identity and the binary on disk are
different facts. Fast status is metadata-only; it does not hash or qualify a
simulator. An old build receipt must not be relabeled after a source change.
Use the Workbench's normal verification, isolated rebuild and relevant
regressions where required. C++ comment edits can change recorded source
hashes even when the intended machine behavior is unchanged.

## Output and artifact policy

Keep raw runs, builds, local workspace configuration and generated sites in
ignored output directories. Keep authored source, deterministic fixtures,
required materialized generated inputs and reproducibility metadata.
[Hygiene policy](HYGIENE.md) explains the existing boundary.

The PR artifact gate examines committed changes against a resolved Git base,
including renames and blobs forced past ignore rules. It does not read dirty
or untracked content and does not retroactively reject unchanged history.
It rejects known runtime-output locations, compiled/cache suffixes and
new or changed blobs larger than 10 MiB. It does not scan file contents or
establish that arbitrary binaries or sensitive content are absent. A source filename containing `generated`
is not itself grounds for rejection. Review legitimate large fixtures
explicitly rather than hiding them with a blanket ignore rule.

Generated documentation HTML/XML, binaries and large raw evidence belong in
local storage or appropriate artifacts, with small committed indexes recording
source/build IDs, checksums, test scope and durable locations. Source-specific
credits and evidence scope travel with any preserved or published result.
