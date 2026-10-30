"""Bind this workbench to an already verified, external SALAM engine.

This copies small, existing receipts without inventing a build or copying the
simulator. It is a current-host migration, not a fresh-machine installer.
"""
import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path

from .configurator import verify_engine
from .configurator_gui_bridge import _verify_generated_outputs
from .fu_capability import inspect_fu_capability
from .runner import file_hash

PROJECT = Path(__file__).resolve().parents[1]
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def verify_build_inputs_receipt(build_path):
    """Verify the exact sidecar needed to replay a configured build identity."""
    build_path = Path(build_path).resolve(strict=True)
    build = json.loads(build_path.read_text(encoding="utf-8"))
    if build.get("kind") != "configured_engine_build" or build.get("state") != "built":
        raise ValueError("Expected a successful configured engine build receipt")
    sidecar = build_path.parent / "source-inputs.json"
    if sidecar.is_symlink() or not sidecar.is_file():
        raise ValueError("Configured build source-inputs.json is missing or symlinked")
    sidecar = sidecar.resolve(strict=True)
    if (
        not isinstance(build.get("source_inputs_sha256"), str)
        or not _SHA256.fullmatch(build["source_inputs_sha256"])
        or file_hash(sidecar) != build["source_inputs_sha256"]
    ):
        raise ValueError("Compiled source-input sidecar differs from build receipt")
    source = json.loads(sidecar.read_text(encoding="utf-8"))
    files = source.get("files")
    if (
        not isinstance(files, dict)
        or not files
        or any(
            not isinstance(name, str)
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
            for name, digest in files.items()
        )
    ):
        raise ValueError("Compiled source-input sidecar has invalid file map")
    digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != source.get("sha256") or digest != build.get("compiled_source_sha256"):
        raise ValueError("Compiled source-input digest differs from build receipt")
    return sidecar


def _receipt(source, relative):
    if (
        not isinstance(relative, str)
        or not relative.startswith("evidence/")
        or "\\" in relative
        or ":" in relative
        or any(part in ("", ".", "..") for part in relative.split("/"))
    ):
        raise ValueError("Receipt must be a safe evidence-relative path")
    path = (source / relative).resolve(strict=True)
    path.relative_to(source)
    if not path.is_file() or path.is_symlink():
        raise ValueError("Receipt is missing or symlinked: " + relative)
    return path


def _copy_exact(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = source.read_bytes()
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != payload:
            raise ValueError("Existing local evidence differs: " + str(destination))
        return
    with destination.open("xb") as stream:
        stream.write(payload)
    if file_hash(destination) != file_hash(source):
        raise ValueError("Copied evidence differs: " + str(destination))


def bootstrap_existing(source_workspace, project=PROJECT):
    source_workspace = Path(source_workspace).resolve(strict=True)
    source = source_workspace.parent
    project = Path(project).resolve(strict=True)
    if source == project or (project / "workspace.json").exists():
        raise ValueError(
            "Target must be a new workbench binding without workspace.json"
        )
    original = json.loads(source_workspace.read_text(encoding="utf-8-sig"))
    selected = original["configuration_engine"]
    engine = Path(selected["path"]).resolve(strict=True)
    if engine == project or engine in project.parents or project in engine.parents:
        raise ValueError("Selected engine must be external to the new workbench")
    if selected.get("distribution") != original["engine"]["distribution"]:
        raise ValueError("Engine distribution differs from workspace selection")
    build = _receipt(source, selected["build_receipt"])
    generation = _receipt(source, selected["generation_receipt"])
    toolchain = _receipt(source, "evidence/toolchain.json")
    build_data = json.loads(build.read_text(encoding="utf-8"))
    if build_data.get("engine") != str(engine):
        raise ValueError("Build receipt belongs to another engine")
    source_inputs_relative = (
        Path(selected["build_receipt"]).parent / "source-inputs.json"
    ).as_posix()
    source_inputs = verify_build_inputs_receipt(build)
    if source_inputs != _receipt(source, source_inputs_relative):
        raise ValueError("Build source-input sidecar path is outside source workspace")
    if build_data.get("toolchain_record", {}).get("sha256") != file_hash(toolchain):
        raise ValueError("Build toolchain record differs from selected source")
    for item in build_data.get("toolchain", []):
        if file_hash(Path(item["path"]).resolve(strict=True)) != item["sha256"]:
            raise ValueError("A recorded build tool has changed: " + item["path"])
    verify_engine(engine, build)
    generation_data = json.loads(generation.read_text(encoding="utf-8"))
    if (
        generation_data.get("state") != "generated"
        or generation_data.get("valid") is not True
    ):
        raise ValueError("Selected hardware generation did not pass")
    _verify_generated_outputs(engine, generation_data)
    capability = inspect_fu_capability(engine, build_receipt=build)
    if not capability["supported"] or not capability["build_verified"]:
        raise ValueError(
            "Selected engine lacks verified FU capability: " + str(capability["reason"])
        )

    required = [
        "evidence/toolchain.json",
        selected["build_receipt"],
        source_inputs_relative,
        selected["generation_receipt"],
    ]
    if selected.get("source_patch_manifest"):
        required.append(selected["source_patch_manifest"])
    fixed = original.get("engine", {})
    if fixed.get("build_receipt"):
        required.append(fixed["build_receipt"])
    for relative in dict.fromkeys(required):
        _copy_exact(_receipt(source, relative), project / relative)
    binding = {
        "schema_version": 1,
        "project": "SALAM Research Workbench",
        "status": "Bound to an existing external engine on this host; no fresh build performed",
        "engine": fixed,
        "configuration_engine": {
            key: selected[key]
            for key in (
                "distribution",
                "path",
                "build_receipt",
                "generation_receipt",
                "source_patch_manifest",
                "verified_capabilities",
                "purpose",
            )
            if key in selected
        },
    }
    with (project / "workspace.json").open("x", encoding="utf-8") as stream:
        json.dump(binding, stream, indent=2)
        stream.write("\n")
    return {
        "state": "bound_existing",
        "engine": str(engine),
        "workspace": str(project / "workspace.json"),
        "copied_receipts": sorted(set(required)),
        "verified_fu_capability": capability["feature"],
        "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-workspace", required=True)
    parser.add_argument("--project", default=str(PROJECT))
    args = parser.parse_args(argv)
    try:
        result = bootstrap_existing(args.source_workspace, args.project)
    except Exception as error:
        result = {
            "state": "failed",
            "errors": [type(error).__name__ + ": " + str(error)],
        }
    print(json.dumps(result))
    return 0 if result["state"] == "bound_existing" else 1


if __name__ == "__main__":
    raise SystemExit(main())
