"""Isolated, fingerprinted hardware source variants for GUI configuration.

A variant is built from a verified independent engine. It never writes its base.
"""
import ast
import datetime
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from . import hardware_codegen
from .configurator import (
    PROJECT,
    build_engine,
    compiled_identity,
    install_hardware_overlay,
    verify_engine,
)
from .toolchain_profile import load_toolchain, record_toolchain

_SKIP_COPY = {
    ".git",
    "__pycache__",
    "m5out",
    "outputs",
    "workbench",
    ".workbench-link-history",
}


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _save(path, record):
    Path(path).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _toolchain_hashes():
    profile = load_toolchain(PROJECT)
    selection = record_toolchain(profile)
    selected_files = list(selection["tools"].values()) + selection.get(
        "llvm_shared_libraries", {}
    ).get("libraries", [])
    paths = [Path(item["path"]).resolve(strict=True) for item in selected_files]
    paths.extend(
        (
            PROJECT / "evidence/toolchain.json",
            Path(hardware_codegen.__file__).resolve(strict=True),
            PROJECT / "salam_workbench/regression.py",
            PROJECT / "salam_workbench/runner.py",
            PROJECT / "salam_workbench/toolchain_profile.py",
        )
    )
    result = {str(path): _sha(path) for path in paths}
    result["selected_toolchain_profile"] = selection["profile_sha256"]
    source_path = PROJECT / "salam_workbench/configurator.py"
    source = source_path.read_text(encoding="utf-8")
    names = {
        "_record",
        "compiled_identity",
        "build_engine",
        "_modern_build_configuration",
        "_safe_generated_debug_object",
        "_debug_label_recovery_objects",
        "_archive_debug_label_objects",
        "_run_build_with_debug_recovery",
        "install_hardware_overlay",
        "verify_engine",
    }
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            segment = ast.get_source_segment(source, node)
            result[str(source_path) + "#" + node.name] = hashlib.sha256(
                segment.encode("utf-8")
            ).hexdigest()
            names.remove(node.name)
    if names:
        raise ValueError(
            "Missing configurator build helper: " + ", ".join(sorted(names))
        )
    return result


def _profile_hashes(base, benchmark, model, period, profile):
    for label, value in (
        ("benchmark", benchmark),
        ("model", model),
        ("period", period),
        ("profile", profile),
    ):
        if not isinstance(value, str) or not hardware_codegen.NAME.fullmatch(value):
            raise ValueError("Invalid hardware " + label)
    folder = (
        base
        / "benchmarks/sys_validation"
        / benchmark
        / "configs/hw_interface/functional_units"
        / model
        / period
        / profile
    )
    folder = folder.resolve(strict=True)
    folder.relative_to(base)
    files = [p for p in folder.rglob("*.yml") if p.is_file()]
    files.append(
        base
        / "benchmarks/sys_validation"
        / benchmark
        / "configs/hw_interface/instructions/inst_list.yml"
    )
    files.extend(base / script for script in hardware_codegen.SCRIPT_FILES)
    if not files:
        raise ValueError("No selected hardware profile files")
    result = {}
    for path in sorted(files):
        resolved = path.resolve(strict=True)
        resolved.relative_to(base)
        if not resolved.is_file():
            raise ValueError("Missing selected hardware profile input")
        result[path.relative_to(base).as_posix()] = _sha(path)
    return result


def _link_plan(base):
    """Preflight all symlinks so a copied build tree cannot write through base."""
    plan = {}
    for folder, directories, filenames in os.walk(str(base), followlinks=False):
        directories[:] = [n for n in directories if n not in _SKIP_COPY]
        for name in directories + filenames:
            link = Path(folder) / name
            if not link.is_symlink():
                continue
            raw = os.readlink(str(link))
            target = (
                (link.parent / raw) if not os.path.isabs(raw) else Path(raw)
            ).resolve(strict=False)
            try:
                inside = target.relative_to(base)
            except ValueError as error:
                raise ValueError("Engine symlink leaves base: " + str(link)) from error
            plan[link.relative_to(base).as_posix()] = {
                "target_relative": inside.as_posix(),
                "absolute": os.path.isabs(raw),
            }
    return plan


def _copy_engine(base, variant, links):
    shutil.copytree(
        str(base),
        str(variant),
        symlinks=True,
        ignore=lambda parent, names: _SKIP_COPY & set(names),
    )
    history = variant / ".workbench-link-history"
    for relative, entry in links.items():
        if entry["absolute"]:
            link = variant / relative
            saved = history / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            link.rename(saved)
            link.symlink_to(variant / entry["target_relative"])
    for relative in links:
        link = variant / relative
        resolved = link.resolve(strict=False)
        try:
            resolved.relative_to(variant)
        except ValueError as error:
            raise ValueError(
                "Variant symlink leaves isolated tree: " + str(link)
            ) from error


def _fingerprint_inputs(
    base, benchmark, model, period, profile, overrides, base_build_receipt
):
    identity = compiled_identity(base)
    return {
        "base_engine": str(base),
        "base_build_receipt": {
            "path": str(base_build_receipt),
            "sha256": _sha(base_build_receipt),
        },
        "base_compiled_source_sha256": identity["sha256"],
        "selected_profile_inputs": _profile_hashes(
            base, benchmark, model, period, profile
        ),
        "selection": {
            "benchmark": benchmark,
            "model": model,
            "period": period,
            "profile": profile,
        },
        "profile_overrides": overrides,
        "toolchain_and_adapter": _toolchain_hashes(),
    }


def _fingerprint(inputs):
    payload = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_variant(variant, manifest, fingerprint, profile_inputs):
    if manifest.get("fingerprint") != fingerprint or manifest.get("state") != "built":
        raise ValueError("Existing variant has a different or incomplete fingerprint")
    build_path = Path(manifest["build_receipt"]).resolve(strict=True)
    verify_engine(variant, build_path)
    generation = json.loads(Path(manifest["generation_receipt"]).read_text())
    if generation.get("state") != "generated" or not generation.get("valid"):
        raise ValueError("Existing variant lacks valid hardware generation")
    for item in generation["outputs"]:
        path = variant / item["relative_path"]
        if not path.is_file() or _sha(path) != item["sha256"]:
            raise ValueError(
                "Existing variant output changed: " + item["relative_path"]
            )
    generated_hashes = {
        item["relative_path"]: item["sha256"] for item in generation["outputs"]
    }
    for relative, source_hash in profile_inputs.items():
        target_path = variant / relative
        expected = generated_hashes.get(relative, source_hash)
        if not target_path.is_file() or _sha(target_path) != expected:
            raise ValueError("Existing variant profile input changed: " + relative)
    return manifest


def ensure_hardware_variant(
    base_engine,
    variant_parent,
    evidence_parent,
    benchmark,
    *,
    model="40nm_model",
    period="5ns",
    profile="default_profile",
    fu_overrides=None,
    base_build_receipt=None,
    jobs=8,
    timeout=7200,
):
    """Generate, install, and build one isolated hardware source variant.

    Returns a durable JSON-safe receipt with engine_path, generation_receipt,
    overlay_receipt, and build_receipt. Existing variants are reused only after
    their source, binary, selected profile, and current toolchain all match.
    """
    base = Path(base_engine).resolve(strict=True)
    variant_parent = Path(variant_parent).resolve()
    evidence_parent = Path(evidence_parent).resolve()
    if not base.is_dir():
        raise ValueError("Base engine must be a directory")
    if (
        variant_parent == base
        or base in variant_parent.parents
        or variant_parent in base.parents
        or evidence_parent == base
        or base in evidence_parent.parents
    ):
        raise ValueError("Variant and evidence roots must be independent of base")
    from .fu_capability import inspect_fu_capability

    capable = inspect_fu_capability(base)["supported"]
    overrides = hardware_codegen._normalize_profile_overrides(
        fu_overrides, allow_fu_limit=capable
    )
    if base_build_receipt is None:
        workspace = json.loads(
            (PROJECT / "workspace.json").read_text(encoding="utf-8-sig")
        )
        configuration = workspace["configuration_engine"]
        if Path(configuration["path"]).resolve(strict=True) != base:
            raise ValueError("Base engine has no selected configured build receipt")
        base_build_receipt = PROJECT / configuration["build_receipt"]
    base_build_receipt = Path(base_build_receipt).resolve(strict=True)
    verify_engine(base, base_build_receipt)
    inputs = _fingerprint_inputs(
        base, benchmark, model, period, profile, overrides, base_build_receipt
    )
    fingerprint = _fingerprint(inputs)
    variant = variant_parent / fingerprint
    marker = variant / ".workbench-variant.json"
    if variant.exists():
        if not marker.is_file():
            raise ValueError("Existing variant is incomplete: " + str(variant))
        saved = json.loads(marker.read_text(encoding="utf-8"))
        _verify_variant(variant, saved, fingerprint, inputs["selected_profile_inputs"])
        return dict(saved, state="reused")
    links = _link_plan(base)
    variant_parent.mkdir(parents=True, exist_ok=True)
    evidence_parent.mkdir(parents=True, exist_ok=True)
    evidence = evidence_parent / (
        "hardware-variant-" + fingerprint[:16] + "-" + uuid.uuid4().hex[:8]
    )
    evidence.mkdir(exist_ok=False)
    record = {
        "schema_version": 1,
        "kind": "salam_hardware_variant",
        "state": "running",
        "fingerprint": fingerprint,
        "fingerprint_inputs": inputs,
        "engine_path": str(variant),
        "evidence_directory": str(evidence),
        "errors": [],
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    _save(evidence / "variant.json", record)
    try:
        generated = hardware_codegen.generate_hardware_code(
            base,
            benchmark,
            evidence / "generation",
            model=model,
            period=period,
            profile=profile,
            profile_overrides=overrides,
            python_executable=load_toolchain(PROJECT)["python"],
        )
        record["generation_receipt"] = str(
            evidence / "generation/hardware-codegen.json"
        )
        if generated.get("state") != "generated" or not generated.get("valid"):
            raise ValueError(
                "Hardware generation failed: "
                + "; ".join(
                    generated.get("errors", [])
                    + generated.get("build_consumer_issues", [])
                )
            )
        _copy_engine(base, variant, links)
        if (
            compiled_identity(variant)["sha256"]
            != inputs["base_compiled_source_sha256"]
        ):
            raise ValueError("Variant source copy differs from verified base")
        overlay = install_hardware_overlay(
            record["generation_receipt"], variant, evidence / "overlay"
        )
        record["overlay_receipt"] = str(evidence / "overlay/overlay.json")
        if overlay.get("state") != "installed_requires_rebuild":
            raise ValueError(
                "Hardware overlay installation failed: "
                + "; ".join(overlay.get("errors", []))
            )
        build = build_engine(variant, evidence / "build", jobs=jobs, timeout=timeout)
        record["build_receipt"] = str(evidence / "build/build.json")
        if build.get("state") != "built":
            raise ValueError(
                "Variant build failed: " + "; ".join(build.get("errors", []))
            )
        verify_engine(variant, record["build_receipt"])
        record["state"] = "built"
        _save(marker, record)
    except Exception as error:
        record["state"] = "failed"
        record["errors"].append(type(error).__name__ + ": " + str(error))
    record["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save(evidence / "variant.json", record)
    if record["state"] == "built":
        _save(marker, record)
    return record
