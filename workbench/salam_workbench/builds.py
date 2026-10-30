"""Versioned build receipt selection; historical evidence is never replaced."""
import json
from pathlib import Path

from .runner import file_hash


def _local_path(project, relative):
    project = Path(project).resolve()
    if not isinstance(relative, str) or not relative:
        raise ValueError("Build receipt must be a nonempty project-relative path")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative:
        raise ValueError("Build receipt must stay inside the project")
    resolved = (project / path).resolve(strict=True)
    resolved.relative_to(project)
    if not resolved.is_file():
        raise ValueError("Build receipt must be a regular file")
    return resolved


def selected_receipt(project):
    project = Path(project).resolve()
    workspace = json.loads((project / "workspace.json").read_text(encoding="utf-8-sig"))
    relative = workspace.get("engine", {}).get(
        "build_receipt", "evidence/engine-artifact.json"
    )
    path = _local_path(project, relative)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema_version") != 1
        or receipt.get("state") != "completed"
    ):
        raise ValueError("Unsupported or unsuccessful engine build receipt")
    return path, receipt


def verify_receipt(project, engine, source_digest):
    path, receipt = selected_receipt(project)
    binary = Path(engine) / "build/ARM/gem5.opt"
    if receipt.get("binary_sha256") != file_hash(binary):
        raise ValueError("Simulator binary differs from the selected build receipt")
    if receipt.get("engine_source_sha256") != source_digest:
        raise ValueError("Engine source differs from the selected build receipt")
    if receipt.get("toolchain_sha256") != file_hash(
        Path(project) / "evidence/toolchain.json"
    ):
        raise ValueError("Toolchain record differs from the selected build receipt")
    return path, receipt


def select_receipt(project, path):
    """Select an already successful receipt without modifying its bytes."""
    project, path = Path(project).resolve(), Path(path).resolve(strict=True)
    relative = path.relative_to(project).as_posix()
    verified = _local_path(project, relative)
    receipt = json.loads(verified.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != 1 or receipt.get("state") != "completed":
        raise ValueError("Cannot select an unsuccessful build")
    workspace_path = project / "workspace.json"
    workspace = json.loads(workspace_path.read_text(encoding="utf-8-sig"))
    workspace.setdefault("engine", {})["build_receipt"] = relative
    temporary = workspace_path.with_suffix(".json.writing")
    temporary.write_text(json.dumps(workspace, indent=2) + "\n", encoding="utf-8")
    temporary.replace(workspace_path)
    return relative


def write_receipt_new(path, receipt):
    """An existing receipt is immutable, including when the new data matches."""
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2)
        handle.write("\n")
