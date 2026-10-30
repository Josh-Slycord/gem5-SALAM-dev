"""Bounded, read-only discovery of real benchmark sources for the desktop UI.

An available configuration is permission to attempt the checked pipeline, not
evidence that the selected source, dataset or configuration passed a simulation.
"""
import re
from pathlib import Path

import yaml

from .config_contract import _Loader
from .gui_editor import extract_components

SUPPORTED_SUITES = (
    "sys_validation",
    "legacy",
    "lenet5-nounroll",
    "mobilenetv2",
)
MAX_BENCHMARKS_PER_SUITE = 512
MAX_CONFIG_BYTES = 2 * 1024 * 1024
_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_FIXED_CHECKS = frozenset(("gemm", "bfs", "nw", "fft", "stencil3d"))
_TITLES = {
    "gemm": "GEMM",
    "bfs": "Breadth-first search",
    "nw": "Needleman–Wunsch",
    "fft": "FFT",
    "stencil3d": "3D stencil",
}


def _inside(path, root):
    """Reject links in the complete path, including links to another local file."""
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        return resolved == path and not path.is_symlink()
    except (OSError, RuntimeError, ValueError):
        return False


def _file(path, root):
    return _inside(path, root) and path.is_file()


def _directory(path, root):
    return _inside(path, root) and path.is_dir()


def _entry(root, suite, directory, *, suite_root=False):
    relative = directory.relative_to(root).as_posix()
    name = directory.name
    warnings = []
    result = {
        "key": relative,
        "benchmark": relative,
        "suite": suite,
        "name": name,
        "title": _TITLES.get(name, name.replace("_", " ")),
        "config_relative": None,
        "availability": "unavailable",
        "can_configure": False,
        "can_run": False,
        "run_readiness": "unavailable",
        "verification": "No simulation result is established by discovery.",
        "description": "Recovered benchmark source; availability is inspected locally.",
        "warnings": warnings,
        "fixed_dataset_check_available": suite == "sys_validation"
        and name in _FIXED_CHECKS,
        "fixed_dataset_check_scope": None,
        "fixed_dataset_runner": None,
        "default_profile_periods": [],
    }
    if result["fixed_dataset_check_available"]:
        result["fixed_dataset_runner"] = "gemm" if name == "gemm" else "regression"
        result["fixed_dataset_check_scope"] = (
            "Separate pinned fixed-dataset runner; arbitrary editor "
            "changes and the selected configuration engine are not covered."
        )
    if not _directory(directory, root):
        warnings.append(
            "Benchmark directory is linked, inaccessible or outside the engine."
        )
        return result
    configs = [directory / filename for filename in ("config.yml", "config.yaml")]
    present = [path for path in configs if path.exists() or path.is_symlink()]
    if not present:
        warnings.append("No config.yml or config.yaml for the checked editor.")
        return result
    if len(present) != 1:
        warnings.append(
            "Both YAML filenames exist; select an unambiguous source layout first."
        )
        result["availability"] = "ambiguous_configuration"
        return result
    config = present[0]
    if not _file(config, root):
        warnings.append("Configuration is linked, inaccessible or outside the engine.")
        return result
    result["config_relative"] = config.relative_to(root).as_posix()
    if suite_root:
        result["availability"] = "unsupported_layout"
        warnings.append(
            "This suite stores its configuration at the suite root. The checked "
            "editor currently requires benchmarks/<suite>/<workload>."
        )
        return result
    try:
        if config.stat().st_size > MAX_CONFIG_BYTES:
            raise ValueError("Configuration exceeds the 2 MiB editor limit")
        documents = list(
            yaml.load_all(config.read_text(encoding="utf-8-sig"), Loader=_Loader)
        )
        if len(documents) != 1:
            raise ValueError("The checked editor supports exactly one YAML document")
        cluster, components = extract_components(documents[0])
        if not components:
            raise ValueError("Configuration has no editable components")
    except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
        result["availability"] = "invalid_configuration"
        warnings.append(
            "Configuration cannot be opened by the checked editor: " + str(error)
        )
        return result
    result.update(
        availability="configurable",
        can_configure=True,
        run_readiness="preflight_required",
        cluster=cluster,
        component_count=len(components),
        verification=(
            "Configured runs check the guest checker, effective configuration and "
            "available direct SALAM traces. This is not an independent numerical oracle."
        ),
        description="Edit this source-backed configuration and attempt the checked simulation pipeline.",
    )
    missing = [
        relative
        for relative in ("Makefile", "hw/Makefile", "sw/Makefile")
        if not _file(directory / relative, root)
    ]
    if missing:
        warnings.append("Missing or unsafe build entry points: " + ", ".join(missing))
        result["run_readiness"] = "missing_build_inputs"
    else:
        result["can_run"] = True
    model = directory / "configs/hw_interface/functional_units/40nm_model"
    if _directory(model, root):
        for period in sorted(model.iterdir(), key=lambda path: path.name):
            profile = period / "default_profile"
            if _NAME.fullmatch(period.name) and _directory(profile, root):
                result["default_profile_periods"].append(period.name)
    if not result["default_profile_periods"]:
        warnings.append(
            "No source-backed 40nm_model/default_profile periods found; choose "
            "an available hardware profile before running."
        )
        result["can_run"] = False
        if result["run_readiness"] == "preflight_required":
            result["run_readiness"] = "hardware_profile_required"
    warnings.append(
        "A successful preflight and fresh run receipts are required for acceptance."
    )
    return result


def discover_benchmarks(engine):
    """Return deterministic rows for the four suites supported by the editor.

    Disabled entries preserve real source layouts that cannot use the current
    checked editor. Discovery reads at most two YAML names per workload and
    never recursively walks a source tree, builds or executes a benchmark.
    """
    root = Path(engine).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Engine must be a directory")
    rows = []
    for suite in SUPPORTED_SUITES:
        suite_path = root / "benchmarks" / suite
        if not suite_path.exists() and not suite_path.is_symlink():
            continue
        if not _directory(suite_path, root):
            rows.append(_entry(root, suite, suite_path, suite_root=True))
            continue
        if any((suite_path / name).exists() for name in ("config.yml", "config.yaml")):
            rows.append(_entry(root, suite, suite_path, suite_root=True))
            # hw/sw are implementation subdirectories, not selectable workloads.
            continue
        candidates = sorted(suite_path.iterdir(), key=lambda path: path.name)
        if len(candidates) > MAX_BENCHMARKS_PER_SUITE:
            raise ValueError(
                "Benchmark suite exceeds the 512-entry discovery limit: " + suite
            )
        for directory in candidates:
            if directory.name == "common" or not _NAME.fullmatch(directory.name):
                continue
            if directory.is_symlink() or directory.is_dir():
                rows.append(_entry(root, suite, directory))
    return rows
