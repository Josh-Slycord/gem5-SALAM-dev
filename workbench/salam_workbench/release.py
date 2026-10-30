"""Curated local release snapshots. Never builds, installs, or publishes."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import uuid

MODEL = "salam_config/data/power_model_40nm.yaml"
CURATED_TREES = ("salam_workbench", "tests", "docs", "experiments")
CURATED_FILES = ("README.md", "workbench.ps1", "workspace.json", "requirements.txt",
                 "requirements-gui.txt", ".gitattributes", ".gitignore", "LICENSE", "COPYING",
                 "CURRENT_CHECKPOINT.md", ".github/workflows/workbench-local.yml")
EXCLUDED = {".git", "__pycache__", ".venv", ".pytest_cache", "build", "dist", "releases"}
MAX_FILE = 256 * 1024 * 1024


class ReleaseError(ValueError):
    pass


def _relative(value):
    if not isinstance(value, str) or not value or value == "." or "\\" in value or ":" in value or "\x00" in value:
        raise ReleaseError("expected a nonempty portable relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ("..", ".") for p in path.parts) or path.as_posix() != value:
        raise ReleaseError("unsafe or noncanonical relative path: " + value)
    return value


def _inside(root, relative):
    relative = _relative(relative)
    root = Path(root).resolve()
    path = root / relative
    for parent in [path] + list(path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ReleaseError("symlink source or parent is unsupported: " + relative)
    try:
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as error:
        raise ReleaseError("missing or escaping path " + relative + ": " + str(error))
    return path


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ReleaseError("cannot read JSON " + str(path) + ": " + str(error))


def _git(root, *arguments):
    argv = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
            "--work-tree=" + str(root), "-C", str(root), *arguments]
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=60, shell=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReleaseError("read-only Git check failed: " + str(error))
    if result.returncode:
        raise ReleaseError("read-only Git check failed: " + result.stderr.strip()[:2000])
    return result.stdout.strip()


def _git_info(root):
    return {"commit": _git(root, "rev-parse", "HEAD"),
            "tree": _git(root, "rev-parse", "HEAD^{tree}"),
            "status_porcelain": _git(root, "status", "--porcelain=v1", "--untracked-files=all")}


def _bundle_header(path):
    heads, prerequisites = [], []
    with Path(path).open("rb") as stream:
        signature = stream.readline(1024).decode("ascii", errors="strict").strip()
        if signature not in ("# v2 git bundle", "# v3 git bundle"):
            raise ReleaseError("unsupported Git bundle header")
        for _ in range(20000):
            raw = stream.readline(4096)
            if raw == b"\n":
                return {"signature": signature, "heads": heads, "prerequisites": prerequisites}
            if not raw or not raw.endswith(b"\n"):
                raise ReleaseError("unterminated or oversized Git bundle header")
            line = raw.decode("ascii", errors="strict").strip()
            if line.startswith("@"):
                continue
            prerequisite = line.startswith("-")
            fields = line.lstrip("-").split(" ", 1)
            if len(fields) != 2 or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", fields[0]):
                raise ReleaseError("invalid Git bundle reference")
            (prerequisites if prerequisite else heads).append({"commit": fields[0], "name": fields[1]})
    raise ReleaseError("too many Git bundle header records")


def _bundle_info(path, engine, commit):
    path = Path(path).resolve(strict=True)
    header = _bundle_header(path)
    if header["prerequisites"]:
        raise ReleaseError("only a full engine bundle with no prerequisites is accepted")
    if commit not in {head["commit"] for head in header["heads"]}:
        raise ReleaseError("bundle does not advertise the accepted engine HEAD")
    verification = _git(engine, "bundle", "verify", str(path))
    return {"path": str(path), "sha256": _sha(path), "bytes": path.stat().st_size,
            "header": header, "git_bundle_verify": "passed", "verification_output": verification[:2000],
            "fresh_restore": "not_performed_by_packager"}


def _walk_files(root, relative):
    path = _inside(root, relative)
    if path.is_file():
        yield relative
        return
    if not path.is_dir():
        raise ReleaseError("not a regular file or directory: " + relative)
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            if (Path(directory) / name).is_symlink():
                raise ReleaseError("symlinks are unsupported in a release selection")
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not d.endswith(".egg-info"))
        for name in sorted(files):
            if name.endswith((".pyc", ".pyo")) or name in ("gem5.opt", "gem5.debug", "gem5.fast"):
                continue
            candidate = Path(directory) / name
            if not candidate.is_file():
                raise ReleaseError("nonregular release source")
            yield candidate.relative_to(root).as_posix()


def _selection(value):
    data = _read_json(value) if isinstance(value, (str, Path)) else value
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ReleaseError("selection schema_version must be 1")
    allowed = {"schema_version", "session_directories", "run_directories", "run_expectations",
               "evidence_files", "workloads", "limitations", "comparisons"}
    if set(data) - allowed:
        raise ReleaseError("unknown selection fields: " + ", ".join(sorted(set(data) - allowed)))
    result = dict(data)
    for field, prefix in (("session_directories", "evidence/"), ("run_directories", "runs/"),
                          ("evidence_files", "evidence/")):
        values = result.get(field, [])
        if not isinstance(values, list) or len(set(map(str, values))) != len(values):
            raise ReleaseError(field + " must be a list without duplicates")
        for value in values:
            _relative(value)
            if not value.startswith(prefix) or any(p in EXCLUDED for p in PurePosixPath(value).parts):
                raise ReleaseError("selection is outside its allowed evidence/run root: " + value)
        result[field] = values
    expected = result.get("run_expectations", {})
    if not isinstance(expected, dict) or set(expected) != set(result["run_directories"]):
        raise ReleaseError("run_expectations must explicitly cover every selected run")
    if any(v not in ("passed", "intentional_failure") for v in expected.values()):
        raise ReleaseError("unsupported selected run expectation")
    comparisons = result.get("comparisons", [])
    if not isinstance(comparisons, list):
        raise ReleaseError("comparisons must be a list")
    records = []
    for comparison in comparisons:
        if not isinstance(comparison, dict) or set(comparison) != {"kind", "runs", "record"}:
            raise ReleaseError("comparison requires kind/runs/record")
        if comparison["kind"] not in ("gem5_repeat_comparison", "gem5_parameter_comparison"):
            raise ReleaseError("unsupported comparison kind")
        pair = comparison["runs"]
        if not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(p, str) for p in pair) or pair[0] == pair[1] or any(expected.get(p) != "passed" for p in pair):
            raise ReleaseError("comparison needs two distinct selected positive runs")
        record = _relative(comparison["record"])
        if not record.startswith("evidence/"):
            raise ReleaseError("comparison record must be selected evidence")
        records.append(record)
    if len(set(records)) != len(records):
        raise ReleaseError("duplicate comparison records")
    result["comparisons"] = comparisons
    workloads = result.get("workloads")
    if not isinstance(workloads, list) or not workloads:
        raise ReleaseError("at least one explicit workload coverage record is required")
    ids = []
    for row in workloads:
        if not isinstance(row, dict) or set(row) != {"id", "status", "evidence", "limitations"}:
            raise ReleaseError("workload rows require id/status/evidence/limitations")
        if not isinstance(row["id"], str) or not row["id"] or row["status"] not in ("supported", "failed", "deferred", "unsupported"):
            raise ReleaseError("invalid workload identity/status")
        ids.append(row["id"])
        if not isinstance(row["evidence"], list) or not isinstance(row["limitations"], list) or any(not isinstance(v, str) for v in row["limitations"]):
            raise ReleaseError("workload evidence/limitations must be lists")
        if row["status"] == "supported" and not row["evidence"]:
            raise ReleaseError("supported workloads require selected evidence")
        for value in row["evidence"]:
            _relative(value)
    if len(set(ids)) != len(ids):
        raise ReleaseError("duplicate workload identifiers")
    if not isinstance(result.get("limitations", []), list) or any(not isinstance(x, str) for x in result.get("limitations", [])):
        raise ReleaseError("limitations must be a string list")
    return result


def _receipt_sources(project, engine):
    from .gemm import engine_source_digest
    from .builds import verify_receipt
    try:
        digest = engine_source_digest(engine)
        path, receipt = verify_receipt(project, engine, digest)
        record_path = Path(receipt["build_record"]).resolve(strict=True)
        relative_record = record_path.relative_to(project).as_posix()
        _inside(project, relative_record)
        record = _read_json(record_path)
        if record.get("state") not in ("passed", "completed") or record.get("return_code", record.get("returncode")) != 0:
            raise ReleaseError("build record does not establish a successful build")
        log_path = _inside(project, (record_path.parent / _relative(record["log"])).relative_to(project).as_posix())
        if _sha(record_path) != receipt["build_record_sha256"] or _sha(log_path) != receipt["build_log_sha256"]:
            raise ReleaseError("build record or log differs from selected receipt")
        return {"path": path.relative_to(project).as_posix(), "record": receipt,
                "engine_source_sha256": digest}, [path.relative_to(project).as_posix(), relative_record,
                                                    log_path.relative_to(project).as_posix()]
    except Exception as error:
        raise ReleaseError("selected build receipt is not ready for packaging: " + str(error))


def _model_info(engine):
    from .model_data import load_model_inventory
    inventory = load_model_inventory(engine)
    if inventory["status"] != "available":
        raise ReleaseError("model source asset is required for this release profile")
    return {"path": "engine-assets/" + MODEL, "sha256": inventory["asset"]["sha256"],
            "declared_model": inventory["declared_model"], "characterization_verified": False,
            "source_confidence": "repository_claim_unverified"}

def inspect_release(project_root, engine_root, selection, *, engine_bundle=None):
    """Return an explicit copy/hash plan without creating directories."""
    project, engine = Path(project_root).resolve(), Path(engine_root).resolve()
    selection = _selection(selection)
    tooling_info, engine_info = _git_info(project), _git_info(engine)
    receipt, receipt_paths = _receipt_sources(project, engine)
    model = _model_info(engine)
    bundle = None
    if engine_bundle is not None:
        if engine_info["status_porcelain"]:
            raise ReleaseError("engine has uncommitted/untracked changes; bundle would omit working bytes")
        bundle = _bundle_info(engine_bundle, engine, engine_info["commit"])
    project_paths = set()
    for relative in CURATED_TREES:
        project_paths.update(_walk_files(project, relative))
    for relative in CURATED_FILES:
        if (project / relative).exists():
            project_paths.add(relative)
    project_paths.update(receipt_paths)
    project_paths.add("evidence/toolchain.json")
    selected_payloads = set()
    for relative in selection["session_directories"] + selection["run_directories"] + selection["evidence_files"]:
        expanded = set(_walk_files(project, relative))
        if selected_payloads.intersection(expanded):
            raise ReleaseError("overlapping selections would duplicate payloads")
        selected_payloads.update(expanded)
    project_paths.update(selected_payloads)
    for row in selection["workloads"]:
        for evidence in row["evidence"]:
            if evidence not in project_paths:
                raise ReleaseError("workload evidence is not an included file: " + evidence)
    for comparison in selection["comparisons"]:
        if comparison["record"] not in project_paths:
            raise ReleaseError("comparison record is not an included file")
    files = []
    def add(path, destination, limit=MAX_FILE):
        size = path.stat().st_size
        if not path.is_file() or size > limit:
            raise ReleaseError("nonregular or oversized payload: " + str(path))
        files.append({"source": str(path), "path": _relative(destination), "bytes": size, "sha256": _sha(path)})
    for relative in sorted(project_paths):
        add(_inside(project, relative), "project/" + relative)
    add(_inside(engine, MODEL), "engine-assets/" + MODEL)
    if files[-1]["sha256"] != model["sha256"]:
        raise ReleaseError("model changed during inspection")
    if bundle:
        add(Path(bundle["path"]), "source/engine.bundle", 2 * 1024 * 1024 * 1024)
    destinations = [f["path"] for f in files]
    if len(set(destinations)) != len(destinations):
        raise ReleaseError("duplicate destination paths")
    return {"schema_version": 1, "kind": "local_release_plan", "status": "ready_to_package",
            "project_root": str(project), "engine_root": str(engine), "selection": selection,
            "tooling": dict(tooling_info, worktree_snapshot=True), "engine": engine_info,
            "receipt": receipt, "bundle": bundle, "files": files,
            "model": model,
            "source_restore": "full_bundle_available_not_restore_tested" if bundle else "external_engine_source_required",
            "rerun": "not_performed_by_packager",
            "coverage_status_authority": "declared_by_selection; saved evidence checked separately",
            "limitations": ["Integrity verification is not authentication or a reproduced experiment.",
                            "Engine binary and build intermediates are excluded; rerunning requires the supported toolchain and a rebuild.",
                            "Model source claims remain unverified; local inclusion is not public redistribution approval."] + selection.get("limitations", [])}


def build_release(project_root, engine_root, selection, *, output_root=None, release_id=None, engine_bundle=None):
    """Create a unique local snapshot. Existing directories are never overwritten."""
    project = Path(project_root).resolve()
    output_path = Path(output_root) if output_root is not None else project / "releases"
    if any(p.is_symlink() for p in [output_path] + list(output_path.parents)):
        raise ReleaseError("release output must not traverse symlinks")
    output = output_path.resolve()
    identifier = release_id or (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", identifier):
        raise ReleaseError("release_id must be a simple directory name")
    target = output / identifier
    if target.exists():
        raise ReleaseError("release destination already exists; choose a new id")
    plan = inspect_release(project, engine_root, selection, engine_bundle=engine_bundle)
    # Output may not sit under a selected source tree or the engine.
    for protected in [Path(engine_root).resolve()] + [project / p for p in CURATED_TREES] + [project / "evidence", project / "runs", project / ".git"]:
        try:
            target.relative_to(protected)
        except ValueError:
            continue
        raise ReleaseError("release output must not be inside source/evidence/run/engine directories")
    output.mkdir(parents=True, exist_ok=True)
    target.mkdir(exist_ok=False)
    manifest = dict(plan, kind="local_research_release", status="assembling", release_id=identifier,
                    created_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    try:
        for entry in plan["files"]:
            destination = target / entry["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            with Path(entry["source"]).open("rb") as source, destination.open("xb") as sink:
                shutil.copyfileobj(source, sink, 1024 * 1024)
            if destination.stat().st_size != entry["bytes"] or _sha(destination) != entry["sha256"] or _sha(entry["source"]) != entry["sha256"]:
                raise ReleaseError("source changed or copy hash failed: " + entry["path"])
        for entry in plan["files"]:
            if _sha(entry["source"]) != entry["sha256"]:
                raise ReleaseError("source changed during package creation: " + entry["path"])
        if _git_info(Path(engine_root).resolve()) != plan["engine"]:
            raise ReleaseError("engine Git state changed during package creation")
        if _git_info(project)["commit"] != plan["tooling"]["commit"]:
            raise ReleaseError("tooling HEAD changed during package creation")
        manifest["status"] = "assembled"
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        with (target / "release.json").open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
        raise ReleaseError("partial release retained at " + str(target) + ": " + str(error))
    with (target / "release.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return {"directory": str(target), "manifest": str(target / "release.json"),
            "validation": verify_release(target)}


def verify_release(directory):
    """Verify copied bytes and saved-run evidence; never execute packaged code."""
    root = Path(directory).resolve()
    manifest = _read_json(_inside(root, "release.json"))
    issues, seen = [], set()
    if not isinstance(manifest, dict) or manifest.get("kind") != "local_research_release" or manifest.get("schema_version") != 1 or manifest.get("status") != "assembled":
        raise ReleaseError("unsupported or incomplete release manifest")
    if not isinstance(manifest.get("files"), list) or not manifest["files"]:
        raise ReleaseError("release files must be a nonempty manifest list")
    for entry in manifest["files"]:
        try:
            relative = _relative(entry["path"])
            if relative in seen:
                raise ReleaseError("duplicate manifest path")
            seen.add(relative)
            path = _inside(root, relative)
            if type(entry.get("bytes")) is not int or entry["bytes"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", "")):
                raise ReleaseError("invalid checksum/size record")
            if not path.is_file() or path.stat().st_size != entry["bytes"] or _sha(path) != entry["sha256"]:
                raise ReleaseError("payload size/hash mismatch")
        except (OSError, KeyError, TypeError, ValueError) as error:
            issues.append(str(entry.get("path") if isinstance(entry, dict) else entry) + ": " + str(error))
    if not seen:
        issues.append("empty release payload")
    actual = set()
    for directory_path, dirs, filenames in os.walk(root, followlinks=False):
        for name in dirs + filenames:
            if (Path(directory_path) / name).is_symlink():
                issues.append("unexpected symlink in release")
        for name in filenames:
            actual.add((Path(directory_path) / name).relative_to(root).as_posix())
    if actual - seen - {"release.json"}:
        issues.append("undeclared release files: " + ", ".join(sorted(actual - seen - {"release.json"})))
    if manifest.get("bundle"):
        try:
            header = _bundle_header(_inside(root, "source/engine.bundle"))
            if header["prerequisites"] or manifest["engine"]["commit"] not in {h["commit"] for h in header["heads"]}:
                issues.append("packaged bundle prerequisites/HEAD do not match")
        except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
            issues.append("packaged bundle header: " + str(error))
    run_checks, comparison_checks = [], []
    try:
        selection = _selection(manifest["selection"])
        required = {"project/evidence/toolchain.json", "engine-assets/" + MODEL, "project/" + _relative(manifest["receipt"]["path"])}
        if manifest.get("bundle"):
            required.add("source/engine.bundle")
        for workload in selection["workloads"]:
            required.update("project/" + path for path in workload["evidence"])
        model_entry = next((entry for entry in manifest["files"] if entry.get("path") == "engine-assets/" + MODEL), {})
        if manifest.get("model", {}).get("sha256") != model_entry.get("sha256") or manifest.get("model", {}).get("characterization_verified") is not False:
            issues.append("model provenance hash or unverified-characterization boundary differs")
        required.update("project/" + c["record"] for c in selection["comparisons"])
        if required - seen:
            issues.append("missing required declared payloads: " + ", ".join(sorted(required - seen)))
        from .report import load_run
        from .runner import _read_correctness
        for relative in selection["run_directories"]:
            expected = selection["run_expectations"][relative]
            run = _inside(root, "project/" + relative)
            loaded = load_run(run)
            if expected == "passed":
                passed = loaded["correctness_verified"]
                reasons = loaded["issues"]
            else:
                raw = _read_correctness(run / "simulator/system.terminal")
                witness = loaded["experiment"].get("negative_witness", {})
                allowed_issues = {"Run state is not passed: failed", "Raw guest correctness evidence or recorded process exit does not satisfy the runner contract"}
                passed = (not (set(loaded["issues"]) - allowed_issues) and loaded["record"].get("return_code") == 0 and
                          loaded["recorded_state"] == "failed" and raw["outcome"] == "failed" and
                          witness.get("expected_runner_state") == "failed" and not loaded["correctness_verified"])
                reasons = [] if passed else ["intentional failure contract not retained"]
            run_checks.append({"path": relative, "expected": expected, "passed": bool(passed), "issues": reasons})
        if any(not r["passed"] for r in run_checks):
            issues.append("saved-run evidence check failed")
        from .report import compare_runs
        from .variant_report import compare_variant_runs
        from .offline_viewer import _metric_identity
        for declared in selection["comparisons"]:
            paths = [_inside(root, "project/" + p) for p in declared["runs"]]
            saved = _read_json(_inside(root, "project/" + declared["record"]))
            comparator = compare_runs if declared["kind"] == "gem5_repeat_comparison" else compare_variant_runs
            fresh = comparator(*paths)
            key = "repeatability_accepted" if declared["kind"] == "gem5_repeat_comparison" else "accepted"
            problems = []
            for field in ("kind", "outcome", key):
                if saved.get(field) != fresh.get(field):
                    problems.append("saved comparison differs from raw recomputation: " + field)
            if fresh.get("kind") != declared["kind"] or fresh.get(key) is not True:
                problems.append("recomputed comparison was not accepted")
            if [r["run_id"] for r in saved["runs"]] != [r["run_id"] for r in fresh["runs"]]:
                problems.append("saved comparison run identities/order differ")
            if _metric_identity(saved.get("metrics")) != _metric_identity(fresh.get("metrics")):
                problems.append("saved metric claims differ from raw recomputation")
            comparison_checks.append({"record": declared["record"], "kind": declared["kind"],
                                      "runs": declared["runs"], "accepted": not problems,
                                      "issues": problems, "metric_count": len(fresh.get("metrics", []))})
        if any(not c["accepted"] for c in comparison_checks):
            issues.append("saved comparison verification failed")
    except Exception as error:
        issues.append("saved-run/comparison validation unavailable: " + str(error))
    return {"schema_version": 1, "kind": "local_release_verification", "directory": str(root),
            "integrity_and_saved_evidence_passed": not issues, "issues": issues,
            "declared_file_count": len(seen), "run_checks": run_checks, "comparison_checks": comparison_checks,
            "rerun": "not_performed", "fresh_engine_restore": "not_performed_by_verifier",
            "authentication": "not_established_by_checksums"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "build"):
        child = commands.add_parser(name)
        child.add_argument("--project", type=Path, required=True)
        child.add_argument("--engine", type=Path, required=True)
        child.add_argument("--selection", type=Path, required=True)
        child.add_argument("--engine-bundle", type=Path)
        if name == "build":
            child.add_argument("--output-root", type=Path)
            child.add_argument("--release-id")
    verify = commands.add_parser("verify")
    verify.add_argument("directory", type=Path)
    options = parser.parse_args(argv)
    try:
        if options.command == "verify":
            result = verify_release(options.directory)
            code = 0 if result["integrity_and_saved_evidence_passed"] else 1
        elif options.command == "inspect":
            result = inspect_release(options.project, options.engine, options.selection, engine_bundle=options.engine_bundle)
            code = 0
        else:
            result = build_release(options.project, options.engine, options.selection, output_root=options.output_root,
                                   release_id=options.release_id, engine_bundle=options.engine_bundle)
            code = 0 if result["validation"]["integrity_and_saved_evidence_passed"] else 1
        print(json.dumps(result, indent=2, allow_nan=False))
        return code
    except (ReleaseError, OSError, UnicodeError) as error:
        print(json.dumps({"status": "rejected", "error": str(error)}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
