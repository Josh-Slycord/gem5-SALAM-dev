"""Evidence-preserving gem5 runner. Fixture tests are not simulator validation."""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import shutil
import subprocess
import time
import uuid

ENV_ALLOWLIST = frozenset({
    "PATH", "M5_PATH", "PYTHONPATH", "LD_LIBRARY_PATH", "LANG", "LC_ALL",
    "LC_CTYPE", "HOME", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TMP", "TEMP",
})
EXPECTED_EXIT_REASON = "m5_exit instruction encountered"
EXIT_RE = re.compile(r"^Exiting @ tick ([0-9]+) because (.+?)\s*$")
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def file_hash(path):
    """Hash one complete, stable regular file; never accept a partial digest."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise OSError("Cannot hash a nonregular file: " + str(path))
        count = 0
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            count += len(block)
        after = os.fstat(handle.fileno())
        if count != before.st_size:
            raise OSError("Incomplete or changed file read while hashing {}: expected {} bytes, read {}".format(
                path, before.st_size, count))
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in fields):
            raise OSError("File changed while hashing: " + str(path))
    return digest.hexdigest()


def _write_json(path, value):
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(path))


def _terminate_owned_process(process):
    """Stop only this runner's still-live subprocess/process group."""
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except ProcessLookupError:
            process.wait()
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    elif os.name == "nt":
        # The PID is from our live Popen handle, never from external input.
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
        process.wait()
    else:
        process.kill()
        process.wait()


def _read_correctness(path):
    evidence = {"guest_output": "simulator/system.terminal", "present": path.is_file(),
                "passed_markers": 0, "failed_markers": 0, "outcome": "missing"}
    if not path.is_file():
        return evidence
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            marker = line.strip()
            if marker == "Check Passed":
                evidence["passed_markers"] += 1
            elif marker == "Check Failed":
                evidence["failed_markers"] += 1
    if evidence["failed_markers"]:
        evidence["outcome"] = "failed"
    elif evidence["passed_markers"]:
        evidence["outcome"] = "passed"
    else:
        evidence["outcome"] = "missing"
    return evidence


def _read_exit_events(path):
    events = []
    if path.is_file():
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = EXIT_RE.match(line.strip())
                if match:
                    events.append({"tick": int(match.group(1)), "reason": match.group(2)})
    return events


def _safe_relative_path(value):
    """Normalize portable relative file paths without accepting traversal or ADS."""
    text = str(value).replace("\\", "/")
    parts = text.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update("COM" + str(i) for i in range(1, 10))
    reserved.update("LPT" + str(i) for i in range(1, 10))
    if any(not part or part in {".", ".."} or part.endswith((" ", "."))
           or any(ord(char) < 32 or char in '<>:"|?*' for char in part)
           or part.split(".", 1)[0].upper() in reserved for part in parts):
        raise ValueError("Expected a safe run-relative file path: " + str(value))
    return "/".join(parts)


def _safe_run_file(run_dir, relative):
    path = run_dir / relative
    try:
        path.resolve().relative_to(run_dir)
        cursor = path
        while cursor != run_dir:
            if cursor.is_symlink():
                return False
            cursor = cursor.parent
        return path.is_file()
    except (OSError, ValueError, RuntimeError):
        return False


def _verify_unchanged(record, item, path, label):
    try:
        after_hash = file_hash(path)
    except OSError:
        after_hash = None
    item["sha256_after_run"] = after_hash
    item["unchanged_after_run"] = after_hash == item["sha256"]
    if not item["unchanged_after_run"]:
        record["errors"].append(label + " changed or disappeared during execution: " + str(path))
        if record["state"] == "passed":
            record["state"] = "incomplete"


def run_experiment(command_prefix, simulator_args, *, cwd, runs_root, experiment,
                   input_paths=(), env_overrides=None, timeout_seconds=600, run_id=None,
                   required_artifacts=(), snapshot_inputs=False):
    """Run one experiment and return its durable run.json record.

    command_prefix normally contains only the gem5 executable. Tests may use a
    Python fixture launcher; that is recorded as fixture evidence by the caller.
    simulator_args begins with the gem5 configuration script. Output placement
    belongs to this API, so caller-supplied -d/--outdir options are rejected.
    run_id collision is an error and never modifies a previous run.
    required_artifacts names files relative to the run directory, for example
    simulator/stats.txt. A missing or unsafe required file prevents success.
    snapshot_inputs copies each declared input (at most 64 MiB per file) into
    inputs/ using numbered basenames. It does not rewrite command arguments;
    original inputs, snapshots and the executable are all checked after running.
    The executable is hashed separately and is not automatically copied.
    """
    root = Path(runs_root).expanduser().resolve()
    identifier = run_id or (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
                            + "-" + uuid.uuid4().hex[:12])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", identifier):
        raise ValueError("run_id must be a single safe directory name")
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / identifier
    run_dir.mkdir(exist_ok=False)  # Never reuse or overwrite an earlier run.
    record = {"schema_version": 1, "run_id": identifier, "run_directory": str(run_dir),
              "state": "planned", "stage": "validation", "started_at": utc_now(),
              "finished_at": None, "argv": [], "cwd": None, "environment": {},
              "timeout_seconds": timeout_seconds, "return_code": None,
              "simulator_exit": None, "correctness": None, "inputs": [],
              "snapshot_inputs": snapshot_inputs, "required_artifacts": [],
              "required_artifact_checks": [],
              "artifacts": [], "warnings": [], "errors": []}
    _write_json(run_dir / "run.json", record)
    process = None
    monotonic_start = time.monotonic()
    try:
        workdir = Path(cwd).expanduser().resolve(strict=True)
        if not workdir.is_dir():
            raise ValueError("cwd must be a directory")
        prefix = [str(x) for x in command_prefix]
        args = [str(x) for x in simulator_args]
        if not prefix or not prefix[0] or not args:
            raise ValueError("command_prefix and simulator_args must be nonempty")
        if any(x.startswith("-d") or x == "--outdir" or x.startswith("--outdir=")
               for x in prefix + args):
            raise ValueError("Output directory is managed by the runner; omit -d/--outdir")
        if not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not isinstance(snapshot_inputs, bool):
            raise ValueError("snapshot_inputs must be a boolean")
        if isinstance(required_artifacts, (str, bytes)):
            raise ValueError("required_artifacts must be a collection of relative paths")
        required_names = set()
        for item in required_artifacts:
            relative = _safe_relative_path(item)
            if relative in {"run.json", "run.json.writing"}:
                raise ValueError("The run record cannot be a required output artifact")
            if relative.casefold() in required_names:
                raise ValueError("Duplicate required artifact: " + relative)
            required_names.add(relative.casefold())
            record["required_artifacts"].append(relative)
        overrides = dict(env_overrides or {})
        if set(overrides) - ENV_ALLOWLIST:
            raise ValueError("Environment override outside allowlist: "
                             + ", ".join(sorted(set(overrides) - ENV_ALLOWLIST)))
        environment = {k: v for k, v in os.environ.items() if k in ENV_ALLOWLIST}
        environment.update({k: str(v) for k, v in overrides.items()})
        record["environment"] = environment
        record["cwd"] = str(workdir)
        program = Path(prefix[0]).expanduser()
        if program.is_absolute() or "/" in prefix[0] or "\\" in prefix[0]:
            executable = program if program.is_absolute() else workdir / program
        else:
            located = shutil.which(prefix[0], path=environment.get("PATH", ""))
            if not located:
                raise FileNotFoundError("Executable not found: " + prefix[0])
            executable = Path(located)
        executable = executable.resolve(strict=True)
        if not executable.is_file():
            raise ValueError("Executable must be a file")
        prefix[0] = str(executable)
        record["executable"] = {"path": str(executable), "sha256": file_hash(executable)}
        _write_json(run_dir / "experiment.json", experiment)
        record["experiment_spec_sha256"] = file_hash(run_dir / "experiment.json")
        for number, item in enumerate(input_paths, 1):
            path = Path(item).expanduser()
            if not path.is_absolute():
                path = workdir / path
            path = path.resolve(strict=True)
            if not path.is_file():
                raise ValueError("Input is not a regular file: " + str(path))
            input_record = {"path": str(path), "bytes": path.stat().st_size,
                            "sha256": file_hash(path)}
            record["inputs"].append(input_record)
            if snapshot_inputs:
                if input_record["bytes"] > MAX_SNAPSHOT_BYTES:
                    raise ValueError("Input exceeds the 64 MiB snapshot limit: " + str(path))
                if "/" in path.name or "\\" in path.name:
                    raise ValueError("Input basename cannot contain snapshot path separators: " + str(path))
                relative = _safe_relative_path("inputs/{:04d}-{}".format(number, path.name))
                destination = run_dir / relative
                destination.parent.mkdir(exist_ok=True)
                if destination.parent.is_symlink() or destination.parent.resolve() != run_dir / "inputs":
                    raise ValueError("Unsafe input snapshot directory")
                # Exclusive creation prevents even an unexpected collision from overwriting evidence.
                with path.open("rb") as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                snapshot = {"path": relative, "bytes": destination.stat().st_size,
                            "sha256": file_hash(destination)}
                input_record["snapshot"] = snapshot
                if snapshot["sha256"] != input_record["sha256"]:
                    raise ValueError("Input changed while taking its snapshot: " + str(path))
        outdir = run_dir / "simulator"
        outdir.mkdir()
        argv = prefix + ["--outdir=" + str(outdir)] + args
        record["argv"] = argv
        record["stage"] = "execution"
        record["state"] = "running"
        _write_json(run_dir / "run.json", record)
        kwargs = {"cwd": str(workdir), "env": environment, "shell": False}
        if os.name == "posix":
            kwargs["start_new_session"] = True
        elif os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        with (run_dir / "stdout.txt").open("wb") as stdout, (run_dir / "stderr.txt").open("wb") as stderr:
            process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, **kwargs)
            record["process_id"] = process.pid
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                record["state"] = "timed_out"
                record["errors"].append("Execution exceeded the declared timeout")
                _terminate_owned_process(process)
        record["return_code"] = process.returncode
        record["stage"] = "assessment"
        guest = _read_correctness(outdir / "system.terminal")
        exits = _read_exit_events(run_dir / "stdout.txt")
        record["correctness"] = guest
        record["simulator_exit_events"] = exits
        record["simulator_exit"] = exits[-1] if exits else None
        if record["state"] != "timed_out":
            if process.returncode != 0 or guest["outcome"] == "failed":
                record["state"] = "failed"
                record["errors"].append("Nonzero process exit or explicit guest correctness failure")
            elif exits and exits[-1]["reason"] != EXPECTED_EXIT_REASON:
                record["state"] = "failed"
                record["errors"].append("Unexpected simulator exit reason")
            elif guest["outcome"] != "passed" or not exits:
                record["state"] = "incomplete"
                record["errors"].append("Required guest correctness evidence or simulator exit reason missing")
            else:
                record["state"] = "passed"
    except (KeyboardInterrupt, SystemExit):
        if process is not None:
            _terminate_owned_process(process)
        record["state"] = "incomplete"
        record["errors"].append("Runner interrupted")
        raise
    except Exception as error:
        if process is not None:
            _terminate_owned_process(process)
        record["state"] = "failed"
        record["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        if "executable" in record:
            _verify_unchanged(record, record["executable"], record["executable"]["path"], "Executable")
        for item in record["inputs"]:
            _verify_unchanged(record, item, item["path"], "Input")
            if "snapshot" in item:
                snapshot = item["snapshot"]
                snapshot_path = run_dir / snapshot["path"]
                if not _safe_run_file(run_dir, snapshot["path"]):
                    snapshot["unchanged_after_run"] = False
                    snapshot["sha256_after_run"] = None
                    record["errors"].append("Unsafe or missing input snapshot: " + snapshot["path"])
                    if record["state"] == "passed":
                        record["state"] = "incomplete"
                else:
                    _verify_unchanged(record, snapshot, snapshot_path, "Input snapshot")
        for artifact in sorted(run_dir.rglob("*")):
            if artifact.name in {"run.json", "run.json.writing"}:
                continue
            try:
                artifact.resolve().relative_to(run_dir)
                outside = False
            except ValueError:
                outside = True
            if artifact.is_symlink() or outside:
                record["errors"].append("External/symlink artifact rejected: " + str(artifact))
                if record["state"] == "passed":
                    record["state"] = "incomplete"
                continue
            if not artifact.is_file():
                continue
            try:
                record["artifacts"].append({"path": artifact.relative_to(run_dir).as_posix(),
                                            "bytes": artifact.stat().st_size, "sha256": file_hash(artifact)})
            except OSError as error:
                record["errors"].append("Artifact read failed: " + type(error).__name__)
                if record["state"] == "passed":
                    record["state"] = "incomplete"
        inventoried = {item["path"] for item in record["artifacts"]}
        for relative in record["required_artifacts"]:
            available = relative in inventoried and _safe_run_file(run_dir, relative)
            record["required_artifact_checks"].append({"path": relative, "available": available})
            if not available:
                record["errors"].append("Required artifact missing, unsafe, or unreadable: " + relative)
                if record["state"] == "passed":
                    record["state"] = "incomplete"
        record["finished_at"] = utc_now()
        record["wall_seconds"] = time.monotonic() - monotonic_start
        _write_json(run_dir / "run.json", record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--runs-root", required=True)
    parser.add_argument("--experiment", required=True, help="JSON experiment description")
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--require-artifact", action="append", default=[], help="Required run-relative output file")
    parser.add_argument("--snapshot-inputs", action="store_true", help="Copy small declared inputs into the run")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--m5-path")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- gem5_binary config.py [config arguments]")
    options = parser.parse_args()
    command = options.command[1:] if options.command[:1] == ["--"] else options.command
    if len(command) < 2:
        parser.error("supply gem5 executable and config script after --")
    experiment_path = Path(options.experiment).resolve()
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    record = run_experiment(command[:1], command[1:], cwd=options.cwd, runs_root=options.runs_root,
                            experiment=experiment, input_paths=[str(experiment_path)] + options.input,
                            env_overrides={"M5_PATH": options.m5_path} if options.m5_path else {},
                            timeout_seconds=options.timeout, required_artifacts=options.require_artifact,
                            snapshot_inputs=options.snapshot_inputs)
    print(json.dumps({"state": record["state"], "run_directory": record["run_directory"]}))
    return 0 if record["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
