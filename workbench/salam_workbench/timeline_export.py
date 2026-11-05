# SPDX-License-Identifier: BSD-3-Clause
"""Export a checked trace without modifying an accepted run's evidence."""
import datetime
import json
import re
import uuid
from pathlib import Path

from .runner import file_hash
from .workbench_results import _roots, _safe


def eligible_traces(result):
    """Only receipt-bound FU artifacts are eligible for desktop export."""
    choices = {}
    for artifact in result.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        name = artifact.get("name", "")
        digest = artifact.get("sha256", "")
        path = artifact.get("path")
        if (
            isinstance(name, str)
            and name.startswith("fu-scheduling-")
            and name.endswith(".json")
            and artifact.get("status") == "hash_verified"
            and isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest)
            and isinstance(path, str)
        ):
            if path in choices and choices[path] != artifact:
                raise ValueError("Conflicting trace artifact identities")
            choices[path] = dict(artifact)
    return sorted(choices.values(), key=lambda value: (value["name"], value["path"]))


def export_selected_trace(result, trace_path, project):
    """Recheck the selected bytes, then export into a new derived directory."""
    from visualizer.export_salam_visualizer import export_trace

    project, roots = _roots(project)
    receipt = _safe(Path(result.get("path", "")), roots)
    expected_receipt = result.get("provenance", {}).get("receipt_sha256")
    if (
        not isinstance(expected_receipt, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_receipt)
        or file_hash(receipt) != expected_receipt
    ):
        raise ValueError("Run receipt changed or has no inspected source identity")
    choices = {item["path"]: item for item in eligible_traces(result)}
    if str(trace_path) not in choices:
        raise ValueError("Choose a hash-verified trace from this recorded run")
    artifact = choices[str(trace_path)]
    source = _safe(Path(trace_path), roots)
    if file_hash(source) != artifact["sha256"]:
        raise ValueError("Trace changed after the result was inspected")
    evidence = project / "evidence"
    if evidence.is_symlink():
        raise ValueError("Evidence directory must not be a symlink")
    evidence.mkdir(exist_ok=True)
    parent = evidence / "execution-timelines"
    if parent.is_symlink():
        raise ValueError("Timeline directory must not be a symlink")
    parent.mkdir(exist_ok=True)
    parent.resolve(strict=True).relative_to(project)
    directory = parent / (
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:10]
    )
    directory.mkdir()
    output = directory / "timeline.html"
    record = {
        "kind": "derived_execution_timeline",
        "schema_version": 1,
        "state": "exporting",
        "source_receipt": str(receipt),
        "source_receipt_sha256": expected_receipt,
        "source_trace": str(source),
        "source_trace_sha256": artifact["sha256"],
        "recorded_run_state": result.get("state", "unknown"),
        "recorded_evidence_assessment": result.get("validation_state", "unknown"),
        "scope": "FU trace replay and visualization; not a numerical correctness check",
        "html": str(output),
    }
    try:
        record["exporter"] = export_trace(
            source, output, expected_sha256=artifact["sha256"]
        )
        if file_hash(source) != artifact["sha256"]:
            raise ValueError("Trace changed during export")
        if file_hash(receipt) != expected_receipt:
            raise ValueError("Run receipt changed during export")
        record["html_sha256"] = file_hash(output)
        record["state"] = "exported"
    except Exception as error:
        record["state"] = "failed"
        record["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        with (directory / "export.json").open("x", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, ensure_ascii=True, allow_nan=False)
            stream.write("\n")
    return record
