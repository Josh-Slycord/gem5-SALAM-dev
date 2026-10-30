"""Bounded, read-only results for the desktop workbench.

Recorded success, replayed guest checks, and independent numerical validation
are separate facts. This reader never launches a simulator or edits evidence.
Call discovery and loading in a worker: trace replay can take several seconds.
"""
import hashlib
import json
import os
import re
from collections import deque
from pathlib import Path

from .runner import (
    EXPECTED_EXIT_REASON,
    _read_correctness,
    _read_exit_events,
    file_hash,
)

MAX_RECEIPT_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_FU_TRACE_BYTES = 512 * 1024 * 1024
MAX_HASH_BYTES = 768 * 1024 * 1024
MAX_DIRECTORIES = 6000
MAX_ARTIFACTS = 512
MAX_METRICS = 3000
RECEIPTS = (
    "gui-execution.json",
    "reference-session.json",
    "configuration.json",
    "run.json",
)
SKIP_DIRECTORIES = frozenset(
    (
        "workspace",
        "tooling-snapshot",
        "source-snapshot",
        "build",
        "inputs",
        "__pycache__",
        ".git",
        "report",
        "reports",
        "simulator",
    )
)
UNIT_NAMES = {
    "simTicks": "tick",
    "simSeconds": "second",
    "simInsts": "instruction",
    "hostSeconds": "second",
    "hostInstRate": "instruction/second",
    "hostTickRate": "tick/second",
    "hostMemory": "byte",
}


def _json(path):
    if path.stat().st_size > MAX_RECEIPT_BYTES:
        raise ValueError("Receipt exceeds the 8 MiB reader limit")

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result

    value = json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError("Nonfinite JSON value: " + value)
        ),
    )
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _roots(project):
    project = Path(project).resolve(strict=True)
    roots = []
    for name in ("evidence", "runs"):
        path = project / name
        if path.is_dir() and not path.is_symlink():
            roots.append(path.resolve())
    return project, roots


def _safe(path, roots, *, directory=False):
    """Reject traversal, symlink components, and paths outside evidence roots."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("Evidence path must be absolute")
    for root in roots:
        try:
            path.relative_to(root)
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
            cursor = path
            while cursor != root:
                if cursor.is_symlink():
                    raise ValueError("Symlinked evidence is unsupported")
                cursor = cursor.parent
            if resolved.is_dir() if directory else resolved.is_file():
                return resolved
        except (OSError, ValueError, RuntimeError):
            continue
    raise ValueError("Evidence is missing, symlinked, or outside this workspace")


def _under(directory, relative, roots):
    text = str(relative).replace("\\", "/")
    if text.startswith("/") or any(p in ("", ".", "..") for p in text.split("/")):
        raise ValueError("Expected a safe evidence-relative path")
    if ":" in text:
        raise ValueError("Unsafe evidence-relative path")
    return _safe(directory / text, roots)


def _benchmark(record, path, roots):
    for field in ("benchmark", "experiment_id"):
        if isinstance(record.get(field), str):
            return record[field]
    spec = record.get("specification")
    if isinstance(spec, dict) and isinstance(spec.get("benchmark"), str):
        return spec["benchmark"]
    for relative in (
        "experiment.json",
        "request.json",
        "normalized-specification.json",
        "specification.json",
    ):
        try:
            value = _json(_under(path.parent, relative, roots))
            if isinstance(value.get("benchmark"), str):
                return value["benchmark"]
        except (OSError, ValueError):
            pass
    return "Unknown benchmark"


def _row(path, record, roots):
    return {
        "path": str(path),
        "run_id": record.get("run_id", path.parent.name),
        "benchmark": _benchmark(record, path, roots),
        "state": record.get("state", "unknown"),
        "status": record.get("state", "unknown"),
        "started_at": record.get("started_at") or "",
        "kind": {
            "gui-execution.json": "GUI configuration run",
            "reference-session.json": "Fixed reference workload",
            "configuration.json": "Configuration pipeline",
            "run.json": "Simulation run",
        }[path.name],
    }


def discover_runs(project, limit=200):
    """Find bounded local receipts without entering generated source/build trees.

    A GUI attempt supersedes its nested pipeline/raw run in the history list.
    Failed attempts without a simulator run are retained. The selected receipt
    still links to its complete underlying artifacts when loaded.
    """
    _, roots = _roots(project)
    queue = deque((root, 0) for root in roots)
    rows, seen = [], set()
    visited = 0
    while queue and visited < MAX_DIRECTORIES:
        directory, depth = queue.popleft()
        visited += 1
        try:
            entries = sorted(os.scandir(str(directory)), key=lambda e: e.name)
        except OSError:
            continue
        names = {entry.name: entry for entry in entries}
        selected = next((name for name in RECEIPTS if name in names), None)
        if selected:
            path = directory / selected
            try:
                path = _safe(path, roots)
                record = _json(path)
                row = _row(path, record, roots)
                if str(path) not in seen:
                    rows.append(row)
                    seen.add(str(path))
            except (OSError, ValueError) as error:
                rows.append(
                    {
                        "path": str(path),
                        "run_id": directory.name,
                        "benchmark": "Unreadable receipt",
                        "state": "unreadable",
                        "status": "unreadable",
                        "started_at": "",
                        "kind": selected,
                        "error": str(error),
                    }
                )
            # Keep one row per configuration attempt rather than three aliases.
            if selected in (
                "gui-execution.json",
                "reference-session.json",
                "configuration.json",
            ):
                continue
        if depth >= 7:
            continue
        for entry in entries:
            if entry.name in SKIP_DIRECTORIES or entry.name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
                queue.append((Path(entry.path), depth + 1))
    rows.sort(key=lambda row: (row["started_at"], row["path"]), reverse=True)
    return rows[: max(1, min(int(limit), 1000))]


def read_artifact_text(path, project, max_bytes=512 * 1024):
    """Preview one safe artifact; keep large logs bounded and binary files inert."""
    _, roots = _roots(project)
    path = _safe(Path(path), roots)
    if type(max_bytes) is not int or max_bytes < 1 or max_bytes > 2 * 1024 * 1024:
        raise ValueError("Artifact preview limit must be 1 byte to 2 MiB")
    with path.open("rb") as stream:
        size = path.stat().st_size
        if size > max_bytes:
            stream.seek(-max_bytes, 2)
        data = stream.read(max_bytes)
    if b"\x00" in data:
        return "Binary artifact · {} bytes\n{}".format(size, path)
    text = data.decode("utf-8", errors="replace")
    if size > max_bytes:
        text = "[Showing final {} bytes of {} bytes]\n".format(max_bytes, size) + text
    return text


def _check(result, name, status, detail, source):
    result["checks"].append(
        {"name": name, "status": status, "detail": str(detail), "source": str(source)}
    )


def _metric(result, name, value, unit, scope, source, status="observed"):
    if len(result["metrics"]) >= MAX_METRICS:
        return
    result["metrics"].append(
        {
            "name": name,
            "value": value,
            "unit": unit,
            "scope": scope,
            "source": str(source),
            "status": status,
        }
    )


def _fu_trace_artifact(path):
    """Large replay quota applies only to actual direct FU invocation paths."""
    path = Path(path)
    return (
        path.parent.name == "observability"
        and path.parent.parent.name == "simulator"
        and re.fullmatch(
            r"fu-scheduling-system(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
            r"\.invocation-[1-9][0-9]*\.json",
            path.name,
        )
        is not None
    )


def _artifact(result, path, roots, expected=None, kind="evidence", budget=None):
    entry = {
        "name": Path(path).name,
        "path": str(path),
        "kind": kind,
        "status": "unavailable",
        "sha256": None,
    }
    try:
        path = _safe(path, roots)
        size = path.stat().st_size
        entry["bytes"] = size
        limit = MAX_FU_TRACE_BYTES if _fu_trace_artifact(path) else MAX_ARTIFACT_BYTES
        if size > limit or (budget is not None and size > budget[0]):
            entry["status"] = "not_checked_size_limit"
        else:
            digest = file_hash(path)
            if path.stat().st_size != size:
                raise OSError("Artifact size changed while hashing")
            if budget is not None:
                budget[0] -= size
            entry["sha256"] = digest
            if expected is None:
                entry["status"] = "present_unbound"
            elif (
                isinstance(expected, str)
                and re.fullmatch(r"[0-9a-fA-F]{64}", expected)
                and digest == expected.lower()
            ):
                entry["status"] = "hash_verified"
            else:
                entry["status"] = "hash_mismatch"
                result["errors"].append("Artifact hash mismatch: " + str(path))
    except (OSError, ValueError) as error:
        entry["detail"] = str(error)
    if len(result["artifacts"]) < MAX_ARTIFACTS:
        result["artifacts"].append(entry)
    return entry


def _linked_receipt(result, item, roots, name, budget):
    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
        return None, None
    try:
        path = _safe(Path(item["path"]), roots)
        artifact = _artifact(result, path, roots, item.get("sha256"), name, budget)
        if artifact["status"] != "hash_verified":
            _check(result, name, "failed", "Linked receipt is not hash verified", path)
            return None, None
        return path, _json(path)
    except (OSError, ValueError) as error:
        result["errors"].append(name + ": " + str(error))
        return None, None


def _direct_salam(result, path, artifact, roots, config_path):
    """Parse direct SALAM files, never infer SALAM timing from system stats."""
    fu_trace = _fu_trace_artifact(path)
    if artifact["status"] != "hash_verified":
        _check(
            result,
            "Direct SALAM artifact",
            "failed"
            if fu_trace or artifact["status"] == "not_checked_size_limit"
            else "unavailable",
            "Direct artifact exceeds a reader quota"
            if artifact["status"] == "not_checked_size_limit"
            else "Missing a matching run-manifest hash",
            path,
        )
        return
    try:
        limit = MAX_FU_TRACE_BYTES if fu_trace else MAX_ARTIFACT_BYTES
        if path.stat().st_size > limit:
            raise ValueError(
                "Direct SALAM JSON exceeds bounded validation limit ({} bytes)".format(
                    limit
                )
            )
        if path.name.startswith("fu-scheduling-") and not fu_trace:
            raise ValueError("Invalid direct FU invocation filename or directory")
        if fu_trace:
            from .fu_experiments import inspect_fu_invocation

            adjacent = path.with_name(path.name[len("fu-scheduling-") :])
            _safe(adjacent, roots)
            inspected = inspect_fu_invocation(path, config_path)
            if inspected.get("source_sha256") != artifact["sha256"]:
                raise ValueError("FU artifact changed between hashing and replay")
            valid = inspected["state"] == "passed"
            _check(
                result,
                "SALAM FU event replay",
                "passed" if valid else "failed",
                "; ".join(str(x) for x in inspected["issues"])
                or (
                    "Complete event replay and lifecycle agree"
                    + (
                        "; effective FU settings agree"
                        if config_path
                        else "; effective config.ini unavailable"
                    )
                ),
                path,
            )
            # Raw direct counters remain useful if replay fails, but carry that state.
            data = json.loads(path.read_text(encoding="utf-8"))
            invocation = data.get("invocation", {})
            number = re.search(r"\.invocation-([0-9]+)\.json$", path.name)
            identity = (
                str(invocation.get("name", path.name))
                + ".invocation-"
                + (number.group(1) if number else "unknown")
            )
            scope = "Direct SALAM accelerator invocation: " + str(identity)
            status = "validated_direct_trace" if valid else "invalid_trace"
            for field, unit in (
                ("elapsed_cycles", "accelerator cycle"),
                ("elapsed_ticks", "tick"),
            ):
                _metric(
                    result,
                    str(identity) + "." + field,
                    invocation.get(field),
                    unit,
                    scope,
                    path,
                    status,
                )
            for item in (inspected.get("trace") or {}).get("units", []):
                for field in (
                    "limit",
                    "attempts",
                    "grants",
                    "denials",
                    "releases",
                    "peak",
                    "outstanding",
                ):
                    _metric(
                        result,
                        str(identity) + "." + item["name"] + "." + field,
                        item.get(field),
                        "count",
                        scope,
                        path,
                        status,
                    )
        else:
            from .observability import load_observability

            inspected = load_observability(path, expected_sha256=artifact["sha256"])
            valid = inspected["contract_valid"]
            identity = inspected.get("identity", {})
            prefix = (
                str(identity.get("accelerator", path.name))
                + ".invocation-"
                + str(identity.get("invocation", "unknown"))
            )
            _check(
                result,
                "SALAM observability contract",
                "passed" if valid else "failed",
                "; ".join(inspected["issues"])
                or "Direct SALAM event aggregates reconcile",
                path,
            )
            for name, item in inspected.get("metrics", {}).items():
                _metric(
                    result,
                    prefix + "." + name,
                    item.get("value"),
                    item.get("unit", "unknown"),
                    "Direct SALAM invocation: "
                    + prefix
                    + "; "
                    + str(item.get("scope") or name),
                    str(path) + str(item.get("source_path") or ""),
                    item.get("availability", "unknown")
                    if valid
                    else "invalid_contract",
                )
            for name, item in inspected.get("unsupported", {}).items():
                _metric(
                    result,
                    prefix + "." + name,
                    None,
                    "unavailable",
                    "Direct SALAM invocation: " + prefix,
                    path,
                    item.get("availability", "unavailable"),
                )
    except (OSError, ValueError, KeyError, TypeError) as error:
        _check(result, "Direct SALAM validation", "failed", str(error), path)


def load_run(path, project):
    """Load a history receipt and its safe, hash-bound local results.

    ``state`` is the recorded overall pipeline state. ``validation_state`` is
    this reader's current evidence assessment. A guest pass never becomes an
    independent numerical pass. Tampering can invalidate a recorded success.
    """
    _, roots = _roots(project)
    path = Path(path)
    if path.is_dir():
        path = next(
            (path / name for name in RECEIPTS if (path / name).is_file()),
            path / "run.json",
        )
    path = _safe(path, roots)
    record = _json(path)
    result = _row(path, record, roots)
    result.update(
        finished_at=record.get("finished_at"),
        metrics=[],
        checks=[],
        artifacts=[],
        errors=list(record.get("errors") or []),
        warnings=list(record.get("warnings") or []),
        provenance={
            "receipt": str(path),
            "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "recorded_state": record.get("state"),
            "independent_numerical_validation": "not_established_by_guest_pass",
            "validation_scope": "Local artifact hashes, guest evidence, and direct SALAM contracts; no calibrated physical-hardware claim",
        },
    )
    budget = [MAX_HASH_BYTES]
    _artifact(result, path, roots, kind="receipt", budget=budget)
    pipeline = record
    pipeline_path = path
    if path.name == "gui-execution.json":
        pipeline_path, pipeline = _linked_receipt(
            result,
            record.get("pipeline_receipt"),
            roots,
            "Configuration pipeline receipt",
            budget,
        )
        witness = record.get("effective_witness") or {}
        _check(
            result,
            "GUI settings reached simulation",
            witness.get("state", "unavailable"),
            str(witness.get("checks", 0))
            + " recorded effective-configuration checks; "
            + str(witness.get("issues", [])),
            path,
        )
        result["provenance"]["source_config"] = record.get("source_config")
        result["provenance"]["engine"] = record.get("selected_engine")
        result["provenance"]["regeneration_plan"] = record.get("regeneration_plan")
    elif path.name == "reference-session.json":
        result["provenance"]["mode"] = record.get("mode", "fixed_reference")
        result["provenance"]["editor_settings_applied"] = (
            record.get("editor_settings_applied") is True
        )
        result["provenance"]["run_directories"] = record.get("run_directories", [])
        result["provenance"]["engine"] = record.get("engine")
        _check(
            result,
            "Fixed reference configuration",
            "recorded",
            "Recovered fixed workload; editor settings were not applied to this reference run",
            path,
        )
        source_session = record.get("source_session")
        if source_session:
            _linked_receipt(
                result,
                {"path": source_session, "sha256": record.get("source_session_sha256")},
                roots,
                "Reference source session",
                budget,
            )
    pipeline = pipeline or {}
    if path.name != "run.json":
        for field, title in (
            ("parameter_witness", "Runtime parameters"),
            ("system_witness", "System settings"),
            ("profile_witness", "Compiled model profile"),
            ("output_transport_witness", "Guest result file transport"),
        ):
            witness = pipeline.get(field)
            if isinstance(witness, dict):
                _check(
                    result,
                    title,
                    witness.get("state", "unknown"),
                    witness.get("issues", []),
                    pipeline_path or path,
                )
        run_directory = pipeline.get("run_directory") or record.get("run_directory")
        try:
            run_path = (
                _safe(Path(run_directory) / "run.json", roots)
                if run_directory
                else None
            )
            raw = _json(run_path) if run_path else {}
        except (OSError, ValueError, TypeError) as error:
            result["errors"].append("Simulation receipt: " + str(error))
            raw, run_path = {}, None
    else:
        raw, run_path = record, path
    if not run_path:
        _check(
            result,
            "Simulation execution",
            "unavailable",
            "No safe local run.json is linked by this attempt",
            path,
        )
        result["validation_state"] = (
            "failed" if result["state"] == "failed" else "incomplete"
        )
        return result
    run_dir = run_path.parent
    _artifact(result, run_path, roots, kind="run receipt", budget=budget)
    result["provenance"]["run_directory"] = str(run_dir)
    result["provenance"]["executable"] = {
        key: (raw.get("executable") or {}).get(key)
        for key in ("path", "sha256", "unchanged_after_run")
    }
    result["provenance"]["argv"] = raw.get("argv", [])
    _check(
        result,
        "Recorded simulation state",
        "passed" if raw.get("state") == "passed" else "failed",
        raw.get("state", "unknown"),
        run_path,
    )
    result["errors"].extend(
        x for x in raw.get("errors", []) if x not in result["errors"]
    )
    if result["benchmark"] == "Unknown benchmark":
        result["benchmark"] = _benchmark(raw, run_path, roots)
    entries = raw.get("artifacts", [])
    if not isinstance(entries, list):
        entries = []
        result["errors"].append("Run artifact manifest is not a list")
    artifacts = {}
    for item in entries[:MAX_ARTIFACTS]:
        try:
            relative = item["path"]
            source = _under(run_dir, relative, roots)
            entry = _artifact(
                result, source, roots, item.get("sha256"), "simulation output", budget
            )
            if relative in artifacts:
                result["errors"].append("Duplicate artifact path: " + relative)
            artifacts[relative] = entry
        except (OSError, ValueError, KeyError, TypeError) as error:
            result["errors"].append("Unsafe/missing artifact: " + str(error))
    if len(entries) > MAX_ARTIFACTS:
        result["warnings"].append("Artifact list truncated at " + str(MAX_ARTIFACTS))
    try:
        terminal = _under(run_dir, "simulator/system.terminal", roots)
        if terminal.stat().st_size > MAX_RECEIPT_BYTES:
            raise ValueError("Guest terminal exceeds reader limit")
        guest = _read_correctness(terminal)
        status = (
            "passed"
            if guest["outcome"] == "passed"
            else ("failed" if guest["failed_markers"] else "unavailable")
        )
        if (
            artifacts.get("simulator/system.terminal", {}).get("status")
            != "hash_verified"
        ):
            status = "unavailable"
        _check(
            result,
            "Guest numerical checker",
            status,
            "{} Check Passed; {} Check Failed. This is the benchmark's own checker.".format(
                guest["passed_markers"], guest["failed_markers"]
            ),
            terminal,
        )
        if guest != raw.get("correctness"):
            _check(
                result,
                "Guest summary matches raw output",
                "failed",
                "Recorded summary differs from raw guest output",
                terminal,
            )
    except (OSError, ValueError) as error:
        _check(result, "Guest numerical checker", "unavailable", str(error), run_path)
    try:
        stdout = _under(run_dir, "stdout.txt", roots)
        if stdout.stat().st_size > MAX_RECEIPT_BYTES:
            raise ValueError("Simulator stdout exceeds reader limit")
        events = _read_exit_events(stdout)
        valid = (
            bool(events)
            and events[-1]["reason"] == EXPECTED_EXIT_REASON
            and raw.get("return_code") == 0
        )
        status = "passed" if valid else "failed"
        if artifacts.get("stdout.txt", {}).get("status") != "hash_verified":
            status = "unavailable"
        _check(
            result,
            "Simulator exit",
            status,
            events[-1] if events else "No gem5 exit event",
            stdout,
        )
    except (OSError, ValueError) as error:
        _check(result, "Simulator exit", "unavailable", str(error), run_path)
    if pipeline.get("benchmark_fixture"):
        try:
            from .benchmark_validation import (
                assess_configured_output,
                numerical_output_relative,
            )

            spec_path, spec = _linked_receipt(
                result,
                pipeline.get("specification"),
                roots,
                "Independent numerical specification",
                budget,
            )
            fixture_path, fixture = _linked_receipt(
                result,
                pipeline.get("benchmark_fixture"),
                roots,
                "Generated input fixture",
                budget,
            )
            if spec is None or fixture is None or "benchmark_input" not in spec:
                raise ValueError("Independent numerical evidence is incomplete")
            numerical_relative = numerical_output_relative(pipeline)
            numerical_path = _under(run_dir, numerical_relative, roots)
            if artifacts.get(numerical_relative, {}).get("status") != "hash_verified":
                raise ValueError("Independent numerical output is not hash verified")
            assessment = assess_configured_output(spec, numerical_path, fixture_path)
            result["independent_oracle"] = assessment
            result["provenance"]["independent_numerical_validation"] = assessment[
                "state"
            ]
            _check(
                result,
                "Independent numerical validation",
                assessment["state"],
                "Compared {}/{} complete accelerator outputs; {} mismatches; {}".format(
                    assessment.get("compared_count", 0),
                    assessment.get("expected_count", 0),
                    assessment.get("mismatch_count", 0),
                    assessment.get("issues", []),
                ),
                numerical_path,
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            _check(
                result,
                "Independent numerical validation",
                "failed",
                str(error),
                run_path,
            )
    else:
        _check(
            result,
            "Independent numerical validation",
            "not_established",
            "A guest Check Passed marker alone does not independently prove every output value. See workload-specific oracle and negative-control evidence.",
            run_path,
        )
    system_metrics = []
    try:
        from .report import parse_stats

        stats_path = _under(run_dir, "simulator/stats.txt", roots)
        if stats_path.stat().st_size > MAX_ARTIFACT_BYTES:
            raise ValueError("stats.txt exceeds bounded reader limit")
        stats = parse_stats(stats_path)
        verified = (
            artifacts.get("simulator/stats.txt", {}).get("status") == "hash_verified"
        )
        _check(
            result,
            "gem5 statistics integrity",
            "passed" if verified and not stats["issues"] else "failed",
            stats["issues"]
            or "Final complete dump; artifact hash matches run manifest",
            stats_path,
        )
        scope = "gem5 final complete statistics dump; full guest including setup, accelerator wait and CPU checker"
        for name, item in stats["metrics"].items():
            system_metrics.append(
                {
                    "name": name,
                    "value": item.get("value"),
                    "unit": UNIT_NAMES.get(name, "see metric description"),
                    "scope": scope,
                    "source": str(stats_path) + ":" + str(item.get("line", "")),
                    "status": item.get("status", "unknown")
                    if verified
                    else "unverified_artifact",
                }
            )
    except (OSError, ValueError) as error:
        _check(result, "gem5 statistics", "unavailable", str(error), run_path)
    config_path = None
    try:
        config_path = _under(run_dir, "simulator/config.ini", roots)
        if artifacts.get("simulator/config.ini", {}).get("status") != "hash_verified":
            config_path = None
    except (OSError, ValueError):
        pass
    direct_count = 0
    for relative, artifact in sorted(artifacts.items()):
        if relative.startswith("simulator/observability/") and relative.endswith(
            ".json"
        ):
            direct_count += 1
            _direct_salam(result, Path(artifact["path"]), artifact, roots, config_path)
    if not direct_count:
        _check(
            result,
            "Direct SALAM metrics",
            "unavailable",
            "This run has no recorded direct SALAM observability JSON; system stats are not substituted",
            run_path,
        )
        _metric(
            result,
            "Direct SALAM metrics",
            None,
            "unavailable",
            "Direct accelerator observability",
            run_path,
            "unavailable",
        )
    room = max(0, MAX_METRICS - len(result["metrics"]))
    result["metrics"].extend(system_metrics[:room])
    if len(system_metrics) > room:
        result["warnings"].append(
            "gem5 metric display truncated at {} rows; the full stats.txt remains in artifacts".format(
                room
            )
        )
    result["metrics"].sort(
        key=lambda item: (
            item["scope"].startswith("gem5"),
            item["name"],
            item["source"],
        )
    )
    failed_checks = any(item["status"] == "failed" for item in result["checks"])
    incomplete_checks = any(
        item["status"] == "unavailable"
        for item in result["checks"]
        if item["name"]
        in (
            "Guest numerical checker",
            "Simulator exit",
            "gem5 statistics",
            "GUI settings reached simulation",
            "Simulation execution",
        )
    )
    result["validation_state"] = (
        "failed"
        if result["errors"] or failed_checks
        else ("incomplete" if incomplete_checks else "checked_recorded_evidence")
    )
    return result
