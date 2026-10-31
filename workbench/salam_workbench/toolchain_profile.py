"""Explicit toolchains for independent SALAM runtimes.

An absent profile retains the recorded Ubuntu20/LLVM12 commands exactly.
The gem5 26 profile is opt-in in that workbench's workspace.json. This module
selects commands; only actual probes/builds establish readiness or correctness.
"""
import hashlib
import json
import shlex
import shutil
import subprocess
from pathlib import Path, PurePosixPath

LEGACY_ID = "ubuntu20-llvm12-python38-armgcc9"
MODERN_ID = "gem5-26-retained-salam"
PROJECT = Path(__file__).resolve().parents[1]
_FIELDS = frozenset(
    (
        "python",
        "scons",
        "cxx",
        "python_config",
        "linker",
        "llvm_bin",
        "llvm_config",
        "arm_bin",
        "arm_sysroot",
        "arm_include",
    )
)
_LEGACY = {
    "id": LEGACY_ID,
    "python": "/usr/bin/python3.8",
    "scons": "/usr/bin/scons",
    "cxx": "/usr/bin/g++",
    "python_config": "/usr/bin/python3.8-config",
    "linker": "/usr/bin/ld",
    "llvm_bin": "/usr/lib/llvm-12/bin",
    "llvm_config": "/usr/lib/llvm-12/bin/llvm-config",
    "arm_bin": "/usr/bin",
}
_MODERN = {
    "id": MODERN_ID,
    "python": "/home/jslycord/.venvs/salam26-20261030/bin/python",
    "scons": "/home/jslycord/.venvs/salam26-20261030/bin/scons",
    "cxx": "/usr/bin/g++",
    "python_config": "/usr/bin/python3.12-config",
    "linker": "/usr/bin/ld",
    "llvm_bin": "/usr/lib/llvm-14/bin",
    "arm_sysroot": "/usr/lib/arm-none-eabi",
    "arm_include": "/usr/lib/arm-none-eabi/include",
    "llvm_config": "/usr/bin/llvm-config-14",
    "arm_bin": "/usr/bin",
}


def _linux_path(value, label):
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value == "/"
        or "\\" in value
        or "\x00" in value
        or "\n" in value
        or "\r" in value
        or any(part in (".", "..") for part in value.split("/"))
        or str(PurePosixPath(value)) != value
    ):
        raise ValueError(
            "Toolchain " + label + " must be a normalized absolute Linux path"
        )
    return value


def load_toolchain(project=PROJECT, *, manifest=None):
    """Materialize a declared profile without executing tools or probing PATH."""
    if manifest is None:
        path = Path(project) / "workspace.json"
        manifest = (
            json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
        )
    if not isinstance(manifest, dict):
        raise ValueError("Workspace manifest must be a mapping")
    configuration = manifest.get("configuration_engine", {})
    if not isinstance(configuration, dict):
        raise ValueError("Configuration engine must be a mapping")
    entry = configuration.get("toolchain_profile")
    if entry is None:
        return dict(_LEGACY)
    if isinstance(entry, str):
        entry = {"id": entry}
    if not isinstance(entry, dict) or set(entry) - (_FIELDS | {"id"}):
        raise ValueError("Unknown toolchain profile fields")
    if entry.get("id") not in (LEGACY_ID, MODERN_ID):
        raise ValueError("Unsupported toolchain profile id")
    selected = dict(_MODERN if entry["id"] == MODERN_ID else _LEGACY)
    for key in _FIELDS & set(entry):
        selected[key] = _linux_path(entry[key], key)
    if selected["id"] == LEGACY_ID and selected != _LEGACY:
        raise ValueError("The recorded legacy profile does not permit tool overrides")
    for key in _FIELDS & set(selected):
        _linux_path(selected[key], key)
    return selected


def is_modern(profile):
    return profile["id"] == MODERN_ID


def apply_environment(environment, profile):
    """Apply fixed command search paths; modern runs isolate Python user-site."""
    result = dict(environment)
    prefix = [profile["llvm_bin"]]
    if is_modern(profile):
        prefix += [str(PurePosixPath(profile["python"]).parent), profile["arm_bin"]]
        result["PYTHONNOUSERSITE"] = "1"
        result["PYTHONDONTWRITEBYTECODE"] = "1"
        result["CXX"] = profile["cxx"]
        result["PYTHON_CONFIG"] = profile["python_config"]
    result["PATH"] = ":".join(prefix + [result.get("PATH", "/usr/bin:/bin")])
    return result


def build_argv(profile, *, target="build/ARM/gem5.opt", jobs=8):
    if type(jobs) is not int or not 1 <= jobs <= 32:
        raise ValueError("jobs must be 1..32")
    if target != "build/ARM/gem5.opt":
        raise ValueError("Unsupported configured simulator build target")
    argv = [
        profile["python"],
        profile["scons"],
        target,
        "-j" + str(jobs),
    ]
    if is_modern(profile):
        argv += ["--with-salam", "LLVM_CONFIG=" + profile["llvm_config"]]
    else:
        argv += [
            "CXX=" + profile["cxx"],
            "PYTHON_CONFIG=" + profile["python_config"],
            "USE_KVM=0",
            "PROTOCOL=CHI",
        ]
    return argv


def normalize_system_options(profile, requested):
    """Record explicit ARM CPU class renames while retaining requested intent."""
    effective = dict(requested)
    normalizations = []
    aliases = {
        "DerivO3CPU": "ArmO3CPU",
        "O3CPU": "ArmO3CPU",
        "TimingSimpleCPU": "ArmTimingSimpleCPU",
        "AtomicSimpleCPU": "ArmAtomicSimpleCPU",
        "MinorCPU": "ArmMinorCPU",
    }
    cpu = requested.get("cpu-type")
    if is_modern(profile) and cpu in aliases:
        effective["cpu-type"] = aliases[cpu]
        normalizations.append(
            {
                "option": "cpu-type",
                "requested": cpu,
                "effective": aliases[cpu],
                "reason": "gem5 26 exposes architecture-specific ARM CPU classes",
                "source": "src/arch/arm/ArmCPU.py",
            }
        )
    return {
        "toolchain_profile": profile["id"],
        "requested": dict(requested),
        "effective": effective,
        "normalizations": normalizations,
    }


def require_legacy_harness(project=PROJECT, action="legacy reference harness"):
    """Reject old fixed-layout harnesses before any preparation or simulator run."""
    if is_modern(load_toolchain(project)):
        raise ValueError(
            action + " is unavailable on the gem5 26 profile. Use configurator or "
            "configure with a configured simulation and independent numerical checks."
        )


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tool_files(profile):
    keys = ["python", "scons", "cxx", "python_config", "linker"]
    if is_modern(profile):
        keys += ["llvm_config"]
    return {key: Path(profile[key]).resolve(strict=True) for key in keys}


def profile_identity(profile):
    payload = json.dumps(profile, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _llvm_shared_libraries(profile, environment):
    argv = [profile["llvm_config"], "--libfiles", "--link-shared"]
    completed = subprocess.run(
        argv, env=environment, shell=False, capture_output=True, text=True, timeout=20
    )
    if completed.returncode or len(completed.stdout.encode("utf-8")) > 6000:
        raise ValueError("Selected LLVM shared-library query failed")
    libraries = []
    for name in shlex.split(completed.stdout):
        path = Path(_linux_path(name, "LLVM library")).resolve(strict=True)
        if not path.name.startswith("libLLVM") or not path.is_file():
            raise ValueError(
                "Selected LLVM query did not identify a regular LLVM library"
            )
        libraries.append({"path": str(path), "sha256": _hash(path)})
    if not libraries:
        raise ValueError("Selected LLVM query returned no shared libraries")
    return {"argv": argv, "return_code": completed.returncode, "libraries": libraries}


def _linker_selection(profile, environment):
    """Check the compiler's own linker resolution, rather than assume an override."""
    argv = [profile["cxx"], "-print-prog-name=ld"]
    completed = subprocess.run(
        argv, env=environment, shell=False, capture_output=True, text=True, timeout=20
    )
    output = completed.stdout.strip()
    if (
        completed.returncode
        or not output
        or len(completed.stdout.encode("utf-8")) > 4096
        or "\n" in output
        or "\r" in output
        or "\x00" in output
    ):
        raise ValueError("Compiler-driver linker query failed or was malformed")
    if output.startswith("/"):
        selected = Path(_linux_path(output, "driver linker")).resolve(strict=True)
    else:
        if "/" in output or "\\" in output or output in (".", ".."):
            raise ValueError(
                "Compiler-driver linker query returned an ambiguous relative path"
            )
        located = shutil.which(output, path=environment.get("PATH", "/usr/bin:/bin"))
        if not located:
            raise ValueError(
                "Compiler-driver linker could not be resolved in selected PATH"
            )
        selected = Path(located).resolve(strict=True)
    expected = Path(profile["linker"]).resolve(strict=True)
    if not selected.is_file() or selected != expected:
        raise ValueError(
            "Configured linker does not match compiler-driver selection: "
            + str(expected)
            + " != "
            + str(selected)
        )
    return {
        "argv": argv,
        "return_code": completed.returncode,
        "reported_program": output,
        "resolved_path": str(selected),
        "sha256": _hash(selected),
        "binding": "compiler_driver_default_verified",
    }


def record_toolchain(profile, *, environment=None, versions=False):
    """Hash selected executables and optionally record bounded version probes."""
    files = tool_files(profile)
    record = {
        "kind": "selected_salam_toolchain",
        "schema_version": 1,
        "profile": dict(profile),
        "profile_sha256": profile_identity(profile),
        "adapter": {"path": str(Path(__file__).resolve()), "sha256": _hash(__file__)},
        "tools": {
            key: {"path": str(path), "sha256": _hash(path)}
            for key, path in files.items()
        },
        "readiness_established": False,
        "bindings": {
            "python": "explicit argv interpreter",
            "scons": "explicit argv script",
            "cxx": "environment.CXX" if is_modern(profile) else "scons argument.CXX",
            "python_config": "environment.PYTHON_CONFIG"
            if is_modern(profile)
            else "scons argument.PYTHON_CONFIG",
            "llvm_config": "scons argument.LLVM_CONFIG"
            if is_modern(profile)
            else "recorded legacy build discovery",
            "linker": "compiler-driver resolution query; configured linker must match",
        },
    }
    env = apply_environment(environment or {"PATH": "/usr/bin:/bin"}, profile)
    if is_modern(profile):
        record["llvm_shared_libraries"] = _llvm_shared_libraries(profile, env)
        record["linker_selection"] = _linker_selection(profile, env)
    if not versions:
        return record
    probes = {
        "python": [profile["python"], "--version"],
        "scons": [profile["python"], "-B", profile["scons"], "--version"],
        "cxx": [profile["cxx"], "--version"],
        "python_config": [profile["python_config"], "--includes"],
        "linker": [profile["linker"], "--version"],
    }
    if is_modern(profile):
        probes["llvm"] = [profile["llvm_config"], "--version"]
        probes["clang"] = [profile["llvm_bin"] + "/clang", "--version"]
    results = {}
    for key, argv in probes.items():
        completed = subprocess.run(
            argv, env=env, shell=False, capture_output=True, text=True, timeout=20
        )
        results[key] = {
            "argv": argv,
            "return_code": completed.returncode,
            "output": (completed.stdout + completed.stderr)[:6000],
        }
        if completed.returncode:
            raise ValueError("Selected tool version probe failed: " + key)
    record["version_probes"] = results
    return record
