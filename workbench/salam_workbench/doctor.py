"""Read-only capability checks for explicitly selected SALAM runtimes.

No packages are installed, no build is started, and no simulator is executed.
Only fixed version/import probes and the existing read-only source/receipt
verification functions are used. A pass is readiness evidence, not a run result.
"""
import argparse
import datetime
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

from .toolchain_profile import (
    apply_environment,
    is_modern,
    load_toolchain,
    record_toolchain,
)

PROFILE = "ubuntu20-llvm12-python38-armgcc9"
PYTHON = "/usr/bin/python3.8"
TOOL_CHECKS = (
    (
        "clang",
        ("/usr/lib/llvm-12/bin/clang", "--version"),
        "12.0.0",
        r"clang version (\d+\.\d+\.\d+)",
    ),
    (
        "llvm",
        ("/usr/lib/llvm-12/bin/llvm-config", "--version"),
        "12.0.0",
        r"^(\d+\.\d+\.\d+)",
    ),
    (
        "gcc",
        ("/usr/bin/gcc", "-dumpfullversion", "-dumpversion"),
        "9.4.0",
        r"^(\d+\.\d+\.\d+)",
    ),
    (
        "gxx",
        ("/usr/bin/g++", "-dumpfullversion", "-dumpversion"),
        "9.4.0",
        r"^(\d+\.\d+\.\d+)",
    ),
    (
        "arm_gcc",
        ("/usr/bin/arm-none-eabi-gcc", "--version"),
        "9.2.1 20191025",
        r"(\d+\.\d+\.\d+\s+\d{8})",
    ),
    (
        "arm_gxx",
        ("/usr/bin/arm-none-eabi-g++", "--version"),
        "9.2.1 20191025",
        r"(\d+\.\d+\.\d+\s+\d{8})",
    ),
    (
        "scons",
        (PYTHON, "-B", "/usr/bin/scons", "--version"),
        "3.1.2",
        r"(?:engine|SCons):\s*v(\d+\.\d+\.\d+)",
    ),
    (
        "make",
        ("/usr/bin/make", "--version"),
        "available",
        r"(GNU Make [^\n]+)",
    ),
    (
        "python_config",
        ("/usr/bin/python3.8-config", "--includes"),
        "Python 3.8 headers",
        r"(python3\.8)",
    ),
)
OPTIONAL_PACKAGES = (
    ("PySide6", "PySide6.QtCore", "6.2.4"),
    ("networkx", "networkx", "3.1"),
    ("numpy", "numpy", "1.24.4"),
)


def _probe(argv, *, cwd=None):
    # Deliberate allowlist. Do not expose a full environment or inherit Python
    # import overrides; HOME is retained because the recorded SCons is user-site.
    env = {
        k: os.environ[k]
        for k in ("HOME", "LANG", "LC_ALL", "TMPDIR")
        if k in os.environ
    }
    env.update(PATH="/usr/lib/llvm-12/bin:/usr/bin:/bin", PYTHONDONTWRITEBYTECODE="1")
    try:
        result = subprocess.run(
            list(argv),
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
        )
        return {
            "argv": list(argv),
            "return_code": result.returncode,
            "output": (result.stdout + result.stderr).strip()[:6000],
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "argv": list(argv),
            "return_code": None,
            "output": "",
            "error": str(error),
        }


def _platform_info():
    release = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                if key in ("ID", "VERSION_ID", "PRETTY_NAME"):
                    release[key] = value.strip('"')
    except OSError:
        pass
    return {
        "system": platform.system(),
        "kernel": platform.release(),
        "distribution": release.get("ID"),
        "distribution_version": release.get("VERSION_ID"),
        "distribution_label": release.get("PRETTY_NAME"),
        "python_version": ".".join(str(v) for v in sys.version_info[:3]),
        "python_executable": str(Path(sys.executable).resolve()),
        "python_prefix": str(Path(sys.prefix).resolve()),
        "expected_python_executable": str(Path(PYTHON).resolve()),
    }


def _check(name, passed, observed, expected, action, **details):
    result = {
        "id": name,
        "status": "pass" if passed else "fail",
        "observed": observed,
        "expected": expected,
        "action": None if passed else action,
    }
    result.update(details)
    return result


def _package_probe(distribution, module):
    # Values come only from fixed calls in this module, never shell interpolation.
    script = (
        "import importlib, importlib.metadata, json; "
        "m=importlib.import_module(" + repr(module) + "); "
        "print(json.dumps({'version':importlib.metadata.version("
        + repr(distribution)
        + "),"
        "'module_path':getattr(m,'__file__',None)}))"
    )
    return _probe((PYTHON, "-B", "-c", script))


def _package_check(distribution, module, expected, optional=False):
    observation = _package_probe(distribution, module)
    try:
        parsed = (
            json.loads(observation["output"]) if observation["return_code"] == 0 else {}
        )
        version = parsed.get("version") if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        version = None
    action = (
        "Optional viewer dependency unavailable or differs from the recorded version; CLI experiments and --inspect do not require the GUI. See requirements-gui.txt and docs/OFFLINE_VIEWER.md."
        if optional
        else "Use the recorded Python3.8 environment with PyYAML6.0.3; do not silently install into or upgrade another interpreter. See docs/ENVIRONMENT.md."
    )
    return _check(
        distribution.lower(),
        version == expected,
        version,
        expected,
        action,
        probe=observation,
    )


def _source_checks(engine, project):
    checks = []
    digest = None
    try:
        from .gemm import BASELINE, engine_source_digest, git

        if not engine.is_dir() or not (engine / "SConstruct").is_file():
            raise ValueError("engine directory with SConstruct is required")
        head = git(engine, "rev-parse", "HEAD").decode().strip()
        baseline_type = git(engine, "cat-file", "-t", BASELINE).decode().strip()
        if baseline_type != "commit":
            raise ValueError("recorded recovered baseline does not resolve to a commit")
        digest = engine_source_digest(engine)
        checks.append(
            _check(
                "source",
                True,
                {
                    "head": head,
                    "baseline": BASELINE,
                    "engine_source_sha256": digest,
                },
                "recorded baseline and hashable engine source",
                "",
            )
        )
    except Exception as error:
        checks.append(
            _check(
                "source",
                False,
                str(error),
                "independent engine with recorded baseline",
                "Use the independent restored engine. Inspect missing baseline/untracked build-source errors; preserve originals and stage new intended engine source before binding a new build.",
            )
        )
    try:
        from .config import validate_gemm_config

        result = validate_gemm_config(
            engine / "benchmarks/sys_validation/gemm/config.yml",
            engine,
            require_ir=False,
        )
        checks.append(
            _check(
                "gemm_contract",
                True,
                {
                    "contract": result.get("contract"),
                    "validation_stage": "prebuild",
                },
                "supported GEMM prebuild configuration",
                "",
            )
        )
    except Exception as error:
        checks.append(
            _check(
                "gemm_contract",
                False,
                str(error),
                "supported GEMM prebuild configuration",
                "Inspect the named field/path using docs/CONFIG_VALIDATION.md. The doctor does not generate configuration or build missing IR.",
            )
        )
    try:
        from .builds import verify_receipt

        if digest is None:
            raise ValueError("source verification failed; receipt cannot be matched")
        path, receipt = verify_receipt(project, engine, digest)
        checks.append(
            _check(
                "build_receipt",
                True,
                {
                    "path": str(path),
                    "binary_sha256": receipt.get("binary_sha256"),
                    "features": receipt.get("features", []),
                },
                "selected completed receipt matches current binary/source/toolchain record",
                "",
            )
        )
    except Exception as error:
        checks.append(
            _check(
                "build_receipt",
                False,
                str(error),
                "selected completed receipt matches current binary/source/toolchain record",
                "Inspect the selected receipt and docs/GEMM_BASELINE.md and docs/GETTING_STARTED.md. Preserve existing evidence. When source changes are intentional and the toolchain passes, deliberately rebuild via gemm reproduce --build-engine; never rewrite hashes to manufacture a pass.",
            )
        )
    return checks


def inspect_environment(engine, *, project_root=None, include_gui=True):
    """Return JSON-ready checks; no build, generation, install, or simulator run."""
    engine = Path(engine).expanduser().resolve()
    project = (
        Path(project_root).resolve()
        if project_root is not None
        else Path(__file__).resolve().parents[1]
    )
    profile = load_toolchain(project)
    if is_modern(profile):
        return _inspect_modern_environment(engine, project, profile, include_gui)
    host = _platform_info()
    supported_os = (
        host["system"] == "Linux"
        and host["distribution"] == "ubuntu"
        and host["distribution_version"] == "20.04"
        and "wsl2" in host["kernel"].lower()
    )
    checks = [
        _check(
            "platform",
            supported_os,
            host,
            "WSL2 Ubuntu20.04",
            "Run this module inside the existing Ubuntu-20.04 WSL2 distribution. Other environments need a separate verified profile; no migration or package changes are performed.",
        ),
        _check(
            "python_runtime",
            host["python_version"] == "3.8.10"
            and host["python_executable"] == host["expected_python_executable"],
            {
                "version": host["python_version"],
                "executable": host["python_executable"],
            },
            {"version": "3.8.10", "executable": PYTHON},
            "Invoke /usr/bin/python3.8 -B -m salam_workbench.doctor in Ubuntu-20.04.",
        ),
    ]
    for name, argv, expected, pattern in TOOL_CHECKS:
        probe = _probe(argv)
        match = re.search(pattern, probe["output"], re.MULTILINE)
        value = match.group(1) if match else None
        if name == "python_config":
            passed = value == "python3.8"
        elif expected == "available":
            passed = value is not None
        else:
            passed = value == expected
        checks.append(
            _check(
                name,
                probe["return_code"] == 0 and passed,
                value,
                expected,
                "Select the recorded executable/version from docs/ENVIRONMENT.md; do not let PATH select LLVM14 or mix LLVM and clang versions. No installer is run by doctor.",
                probe=probe,
            )
        )
    checks.append(_package_check("PyYAML", "yaml", "6.0.3"))
    checks.extend(_source_checks(engine, project))
    optional = []
    if include_gui:
        optional = [
            _package_check(name, module, version, optional=True)
            for name, module, version in OPTIONAL_PACKAGES
        ]
        optional.append(
            {
                "id": "display",
                "status": "available"
                if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
                else "unknown",
                "observed": {
                    "display_variable_present": bool(os.environ.get("DISPLAY")),
                    "wayland_variable_present": bool(os.environ.get("WAYLAND_DISPLAY")),
                },
                "meaning": "Environment hints only; no GUI window or rendering test was performed.",
                "action": "Use offline_viewer --inspect without Qt; rendering can be tested separately with QT_QPA_PLATFORM=offscreen.",
            }
        )
    by_id = {c["id"]: c for c in checks}
    tool_ids = ["platform", "python_runtime", "pyyaml"] + [c[0] for c in TOOL_CHECKS]
    ready = all(c["status"] == "pass" for c in checks)
    return {
        "schema_version": 1,
        "kind": "workbench_environment_check",
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "supported_profile": PROFILE,
        "engine": str(engine),
        "project": str(project),
        "ready": ready,
        "required_checks": checks,
        "optional_checks": optional,
        "failures": [c["id"] for c in checks if c["status"] != "pass"],
        "capabilities": {
            "supported_toolchain": all(by_id[i]["status"] == "pass" for i in tool_ids),
            "source_contract": all(
                by_id[i]["status"] == "pass" for i in ("source", "gemm_contract")
            ),
            "recorded_build_matches": by_id["build_receipt"]["status"] == "pass",
            "reproduce_without_engine_build": ready,
            "optional_gui_dependencies": all(
                c["status"] == "pass" for c in optional if c["id"] != "display"
            )
            if include_gui
            else None,
            "gui_rendering": "not_tested",
            "fresh_distro_installation": "not_verified",
        },
        "limitations": [
            "Version/import checks are not native-header compilation or linker validation.",
            "Receipt verification binds recorded source/binary/toolchain bytes; it does not rerun GEMM or certify current physical hardware performance.",
            "ENVIRONMENT.md describes the verified existing environment; a blank-distro installation was not reproduced.",
            "A mismatched version is outside this exact recorded profile, not proof it can never work.",
        ],
    }


def _profile_probe(profile, argv):
    env = {
        key: os.environ[key]
        for key in ("HOME", "LANG", "LC_ALL", "TMPDIR")
        if key in os.environ
    }
    env = apply_environment(env, profile)
    try:
        result = subprocess.run(
            list(argv), env=env, capture_output=True, text=True, timeout=20, shell=False
        )
        return {
            "argv": list(argv),
            "return_code": result.returncode,
            "output": (result.stdout + result.stderr).strip()[:6000],
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "argv": list(argv),
            "return_code": None,
            "output": "",
            "error": str(error),
        }


def _modern_package_check(profile, distribution, module):
    script = (
        "import importlib,importlib.metadata,json; m=importlib.import_module("
        + repr(module)
        + "); print(json.dumps({'version':importlib.metadata.version("
        + repr(distribution)
        + "),'module_path':getattr(m,'__file__',None)}))"
    )
    probe = _profile_probe(profile, [profile["python"], "-B", "-c", script])
    try:
        observed = json.loads(probe["output"]) if probe["return_code"] == 0 else {}
    except (ValueError, TypeError):
        observed = {}
    passed = isinstance(observed, dict) and bool(observed.get("version"))
    return _check(
        distribution.lower(),
        passed,
        observed,
        "importable in selected isolated runtime; observed version recorded",
        "Use the isolated gem5 26 dependency environment; this check does not install packages or certify the legacy GUI lock.",
        probe=probe,
    )


def _modern_source_checks(engine, project):
    from .configurator import compiled_identity, verify_engine

    checks = []
    try:
        identity = compiled_identity(engine)
        checks.append(
            _check(
                "source",
                True,
                {
                    "compiled_source_sha256": identity["sha256"],
                    "file_count": len(identity["files"]),
                },
                "hashable retained SALAM/gem5 26 compiled sources",
                "",
            )
        )
    except Exception as error:
        checks.append(
            _check(
                "source",
                False,
                str(error),
                "hashable retained SALAM/gem5 26 compiled sources",
                "Inspect the isolated source checkout; no build is performed.",
            )
        )
    try:
        manifest = json.loads(
            (project / "workspace.json").read_text(encoding="utf-8-sig")
        )
        relative = manifest["configuration_engine"]["build_receipt"]
        receipt = (project / relative).resolve(strict=True)
        receipt.relative_to(project)
        if not receipt.is_file():
            raise ValueError("Configured build receipt is not a regular file")
        observed = verify_engine(engine, receipt)
        checks.append(
            _check(
                "configured_build_receipt",
                True,
                observed,
                "selected completed configured build matches current source/binary/toolchain",
                "",
            )
        )
    except Exception as error:
        checks.append(
            _check(
                "configured_build_receipt",
                False,
                str(error),
                "selected completed configured build matches current source/binary/toolchain",
                "Complete an explicit isolated configured build and select its receipt; legacy reference receipts do not establish gem5 26 readiness.",
            )
        )
    return checks


def _inspect_modern_environment(engine, project, profile, include_gui):
    host = _platform_info()
    prefix = str(Path(profile["python"]).parent.parent.resolve())
    platform_ok = (
        host["system"] == "Linux"
        and host["distribution"] == "ubuntu"
        and host["distribution_version"] == "24.04"
        and "wsl2" in host["kernel"].lower()
    )
    runtime_ok = (
        host["python_version"].startswith("3.12.")
        and host.get("python_prefix") == prefix
        and host["python_executable"] == str(Path(profile["python"]).resolve())
    )
    checks = [
        _check(
            "platform",
            platform_ok,
            host,
            "isolated WSL2 Ubuntu24.04 gem5 26 runtime",
            "Run inside the selected Ubuntu-24.04 distribution.",
        ),
        _check(
            "python_runtime",
            runtime_ok,
            {
                "version": host["python_version"],
                "executable": host["python_executable"],
                "prefix": host.get("python_prefix"),
            },
            {"python": profile["python"], "prefix": prefix, "version": "3.12.x"},
            "Invoke doctor with the selected isolated Python; system/user-site packages are not an equivalent environment.",
        ),
    ]
    snapshot = None
    try:
        snapshot = record_toolchain(profile, versions=True)
        versions = snapshot["version_probes"]
        llvm = re.search(r"^(14\.\d+\.\d+)", versions["llvm"]["output"])
        clang = re.search(r"clang version (14\.\d+\.\d+)", versions["clang"]["output"])
        scons = re.search(
            r"(?:engine|SCons):\s*v(\d+\.\d+\.\d+)", versions["scons"]["output"]
        )
        headers = "python3.12" in versions["python_config"]["output"]
        matched = bool(
            llvm
            and clang
            and llvm.group(1) == clang.group(1)
            and scons
            and int(scons.group(1).split(".")[0]) >= 4
            and headers
        )
        checks.append(
            _check(
                "selected_toolchain",
                matched,
                snapshot,
                "selected executables resolve; matching LLVM/Clang14; SCons4+; Python3.12 headers",
                "Inspect selected tool version probes and paths; no package or source changes are performed.",
            )
        )
    except Exception as error:
        checks.append(
            _check(
                "selected_toolchain",
                False,
                str(error),
                "resolvable selected tools and bounded version probes",
                "Inspect missing selected paths; do not fall back to legacy tools.",
            )
        )
    for name in ("arm-none-eabi-gcc", "arm-none-eabi-g++", "make"):
        argv = [
            str(Path(profile["arm_bin"]) / name) if name != "make" else "/usr/bin/make",
            "--version",
        ]
        probe = _profile_probe(profile, argv)
        checks.append(
            _check(
                name,
                probe["return_code"] == 0 and bool(probe["output"]),
                probe,
                "available; exact version recorded",
                "Supply this tool in the selected isolated runtime; no install is performed.",
            )
        )
    checks.append(_modern_package_check(profile, "PyYAML", "yaml"))
    tool_ready = all(check["status"] == "pass" for check in checks)
    source_checks = _modern_source_checks(engine, project)
    checks.extend(source_checks)
    optional = (
        [
            _modern_package_check(profile, name, module)
            for name, module in (
                ("PySide6", "PySide6.QtCore"),
                ("networkx", "networkx"),
                ("numpy", "numpy"),
            )
        ]
        if include_gui
        else []
    )
    ready = all(check["status"] == "pass" for check in checks)
    return {
        "schema_version": 1,
        "kind": "workbench_environment_check",
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "supported_profile": profile["id"],
        "engine": str(engine),
        "project": str(project),
        "ready": ready,
        "required_checks": checks,
        "optional_checks": optional,
        "failures": [check["id"] for check in checks if check["status"] != "pass"],
        "capabilities": {
            "supported_toolchain": tool_ready,
            "source_contract": source_checks[0]["status"] == "pass",
            "recorded_build_matches": source_checks[1]["status"] == "pass",
            "configured_simulation_ready": ready,
            "reproduce_without_engine_build": False,
            "legacy_reference_mode": "unavailable_on_modern_profile",
            "optional_gui_dependencies": all(
                check["status"] == "pass" for check in optional
            )
            if include_gui
            else None,
            "gui_rendering": "not_tested",
            "numerical_simulations": "not_tested",
            "fresh_distro_installation": "not_verified",
        },
        "limitations": [
            "The modern profile retains our SALAM model and controls; it does not adopt the changed native upstream SALAM schema.",
            "Version/import/source/receipt checks do not execute a numerical simulation or GUI rendering test.",
            "Configured builds require their own source/binary/toolchain receipt; accepted Ubuntu20 reference runs are separate evidence.",
            "Package versions are observations of the isolated modern runtime, not validation against the legacy Python3.8 GUI lock.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="skip optional GUI package probes",
    )
    args = parser.parse_args(argv)
    result = inspect_environment(
        args.engine,
        project_root=args.project_root,
        include_gui=not args.no_gui,
    )
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
