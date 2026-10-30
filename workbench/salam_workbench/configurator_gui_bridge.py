"""Checked preparation bridge for the isolated legacy SALAM GUI.

The GUI button prepares the selected on-disk YAML in a fresh evidence
workspace. It never starts a simulator. GUI form edits remain separate until
the editor schema is migrated to the checked configuration contract.
"""
import argparse
import ast
import datetime
import difflib
import hashlib
import json
import re
import shutil
import sys
import uuid
from pathlib import Path

from .configurator import run_configuration, validate_spec, verify_engine

PROJECT = Path(__file__).resolve().parents[1]
ORIGINAL_GUI_SHA256 = "1df44c5a7a1b8215804985982061c9b9ec61636fd82413f5168cf46010bec0f6"
GUI_RELATIVE = Path("gem5-SALAM-gui/src/gui/config_generator.py")


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _save(path, record):
    Path(path).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _project_file(project, relative):
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or ":" in relative
    ):
        raise ValueError("Manifest path must be project relative")
    path = (project / relative).resolve(strict=True)
    path.relative_to(project)
    if not path.is_file():
        raise ValueError("Manifest path is not a regular file")
    return path


def _verify_generated_outputs(engine, generation):
    outputs = generation.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("Hardware generation receipt has no outputs")
    kinds = {}
    seen = set()
    for item in outputs:
        relative = item.get("relative_path") if isinstance(item, dict) else None
        digest = item.get("sha256") if isinstance(item, dict) else None
        kind = item.get("kind") if isinstance(item, dict) else None
        if (
            not isinstance(relative, str)
            or not re.fullmatch(r"[A-Za-z0-9._/-]+", relative)
            or any(part in ("", ".", "..") for part in relative.split("/"))
            or relative in seen
        ):
            raise ValueError("Invalid or duplicate generated output path")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid generated output hash")
        if kind not in (
            "compiled_source",
            "simobject_source",
            "build_declaration",
            "profile_data",
        ):
            raise ValueError("Unknown generated output kind")
        seen.add(relative)
        target = engine / relative
        resolved = target.resolve(strict=True)
        resolved.relative_to(engine)
        if resolved != target or not target.is_file() or _sha(target) != digest:
            raise ValueError(
                "Generated output differs from independent engine: " + relative
            )
        kinds[kind] = kinds.get(kind, 0) + 1
    for required in (
        "compiled_source",
        "simobject_source",
        "build_declaration",
    ):
        if not kinds.get(required):
            raise ValueError("Generation receipt lacks " + required + " outputs")
    return {"matched_outputs": len(seen), "kinds": kinds}


def _selected_config(engine, benchmark, config):
    if not isinstance(benchmark, str) or not re.fullmatch(
        r"benchmarks/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+", benchmark
    ):
        raise ValueError("Selected benchmark must be benchmarks/<suite>/<workload>")
    expected = benchmark + "/"
    if (
        not isinstance(config, str)
        or not config.startswith(expected)
        or not config.endswith(("/config.yml", "/config.yaml"))
    ):
        raise ValueError(
            "Selected YAML must be config.yml or config.yaml in the benchmark"
        )
    relative = Path(config)
    if relative.parts[:-1] != Path(benchmark).parts:
        raise ValueError("Selected YAML escapes the benchmark")
    path = (engine / relative).resolve(strict=True)
    path.relative_to(engine)
    if path != engine / relative or not path.is_file():
        raise ValueError(
            "Selected YAML must be a regular file inside the independent engine"
        )
    return path


def prepare_selected(
    engine_root,
    benchmark,
    config,
    *,
    distro,
    requested_period,
    project=PROJECT,
    evidence_dir=None,
):
    """Prepare selected YAML; only a fresh structured pipeline receipt can pass."""
    project = Path(project).resolve(strict=True)
    directory = (
        Path(evidence_dir)
        if evidence_dir is not None
        else project
        / "evidence"
        / (
            "gui-prepare-"
            + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
            + "-"
            + uuid.uuid4().hex[:8]
        )
    ).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    record = {
        "schema_version": 1,
        "kind": "checked_gui_prepare",
        "state": "planned",
        "evidence_directory": str(directory),
        "selected_benchmark": benchmark,
        "selected_config": config,
        "requested_distro": distro,
        "requested_period": requested_period,
        "editor_form_applied": False,
        "simulation_requested": False,
        "errors": [],
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    _save(directory / "gui-prepare.json", record)
    try:
        manifest_path = project / "workspace.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        configuration = manifest["configuration_engine"]
        expected_engine = Path(configuration["path"]).resolve(strict=True)
        engine = Path(engine_root).resolve(strict=True)
        if engine != expected_engine:
            raise ValueError(
                "GUI selected engine is not the independent configuration engine"
            )
        if distro != configuration["distribution"]:
            raise ValueError(
                "GUI WSL distribution differs from configuration-engine manifest"
            )
        record["workspace_manifest"] = {
            "path": str(manifest_path),
            "sha256": _sha(manifest_path),
        }
        selected = _selected_config(engine, benchmark, config)
        record["yaml_source"] = {
            "path": str(selected),
            "sha256": _sha(selected),
        }
        gui_source = engine / GUI_RELATIVE
        if gui_source.is_file():
            record["gui_source"] = {
                "path": str(gui_source),
                "sha256": _sha(gui_source),
            }

        generation_path = _project_file(project, configuration["generation_receipt"])
        generation = json.loads(generation_path.read_text(encoding="utf-8"))
        if generation.get("state") != "generated" or not generation.get("valid"):
            raise ValueError(
                "Selected hardware profile has no valid generation receipt"
            )
        record["generated_engine_match"] = _verify_generated_outputs(engine, generation)
        actual_period = generation.get("selection", {}).get("period")
        record["compiled_profile"] = {
            "generation_receipt": str(generation_path),
            "generation_sha256": _sha(generation_path),
            "period": actual_period,
            "model": generation.get("selection", {}).get("model"),
            "profile": generation.get("selection", {}).get("profile"),
        }
        if requested_period != actual_period:
            raise ValueError(
                "GUI cycle time differs from compiled profile period; rebuild hardware first"
            )
        build_path = _project_file(project, configuration["build_receipt"])
        record["simulator_identity"] = verify_engine(engine, build_path)
        record["compiled_profile"]["build_receipt"] = str(build_path)

        name = Path(benchmark).name
        spec = {
            "schema_version": 1,
            "name": name,
            "benchmark": benchmark,
            "config": config,
            "import_format": "legacy_gui",
        }
        validate_spec(spec)
        spec_path = directory / "specification.json"
        _save(spec_path, spec)
        record["specification"] = {
            "path": str(spec_path),
            "sha256": _sha(spec_path),
        }
        record["state"] = "preparing"
        _save(directory / "gui-prepare.json", record)
        pipeline = run_configuration(
            engine, spec_path, directory / "pipeline", simulate=False
        )
        pipeline_path = directory / "pipeline/configuration.json"
        disk_pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))
        record["pipeline"] = {
            "path": str(pipeline_path),
            "sha256": _sha(pipeline_path),
            "state": disk_pipeline.get("state"),
        }
        if (
            pipeline.get("state") != "prepared"
            or disk_pipeline.get("state") != "prepared"
            or not disk_pipeline.get("generated_after_build")
            or disk_pipeline.get("simulation_requested") is not False
        ):
            raise ValueError("Checked preparation did not produce a prepared receipt")
        if _sha(selected) != record["yaml_source"]["sha256"]:
            raise ValueError("Selected YAML changed during preparation")
        record["state"] = "prepared"
    except Exception as error:
        record["state"] = "failed"
        record["errors"].append(type(error).__name__ + ": " + str(error))
    record["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _save(directory / "gui-prepare.json", record)
    return record


_GUI_METHODS = '''    def generate_files(self):
        """Prepare the selected on-disk YAML through the checked workbench."""
        import json
        import re
        import subprocess

        self.validation_output.clear()
        try:
            independent = Path(__file__).resolve().parents[3]
            selected_engine = self.gem5_path.resolve(strict=True)
            if selected_engine != independent:
                raise ValueError("Select this independent configurator-engine checkout first")
            bench_name = self.benchmark_combo.currentData()
            bench_dir = self.bench_dir_combo.currentText()
            if not isinstance(bench_name, str) or not re.fullmatch(
                    r"[A-Za-z0-9_-]+", bench_name):
                raise ValueError("Select a benchmark before preparation")
            if bench_dir not in (
                    "benchmarks/sys_validation", "benchmarks/legacy",
                    "benchmarks/lenet5-nounroll", "benchmarks/mobilenetv2"):
                raise ValueError("Benchmark directory is not an allowed GUI selection")
            benchmark = bench_dir + "/" + bench_name
            choices = [selected_engine / benchmark / "config.yml",
                       selected_engine / benchmark / "config.yaml"]
            selected_yaml = next((path for path in choices if path.is_file()), None)
            if selected_yaml is None:
                raise ValueError("Selected benchmark has no on-disk config.yml or config.yaml")
            selected_yaml.resolve(strict=True).relative_to(independent)
            self.validation_output.append("Preparing selected on-disk YAML: " + str(selected_yaml))
            self.validation_output.append(
                "Unsaved form/global fields are not applied by this action. "
                "The cycle-time choice must match the verified compiled profile.")
            summary = self._run_checked_prepare(
                benchmark, benchmark + "/" + selected_yaml.name)
            self.validation_output.append("Evidence: " + str(summary.get("evidence_directory")))
            if summary.get("state") != "prepared":
                raise ValueError("; ".join(summary.get("errors", [])) or
                                 "Checked preparation did not pass")
            self.validation_output.append(
                "Prepared: generated topology and headers, fresh guest ELF and LLVM IR. "
                "No simulation was run.")
            QMessageBox.information(self, "Preparation Complete",
                                    "Checked preparation completed. See the evidence path above.")
        except Exception as error:
            self.validation_output.append("Preparation failed: " + str(error))
            QMessageBox.warning(self, "Preparation Failed", str(error))

    @staticmethod
    def _checked_wsl_path(path, distro):
        raw = str(path)
        win = raw.replace("/", "\\\\")
        if win.startswith("\\\\\\\\wsl$\\\\") or win.startswith("\\\\\\\\wsl.localhost\\\\"):
            parts = win.split("\\\\")
            if len(parts) < 5 or parts[3].lower() != distro.lower():
                raise ValueError("WSL share path does not match selected distribution")
            return "/" + "/".join(parts[4:])
        from utils.wsl import windows_to_wsl_path
        return windows_to_wsl_path(raw)

    def _run_checked_prepare(self, benchmark, config):
        import json
        import os
        import subprocess

        parent = self.parent()
        distro = parent.wsl_status.get_selected_distro() if (
            parent and hasattr(parent, "wsl_status")) else None
        if not distro:
            raise ValueError("Select a WSL distribution in the main window")
        engine = self._checked_wsl_path(self.gem5_path, distro)
        workbench = Path(os.environ.get("SALAM_WORKBENCH_ROOT") or
                         Path(__file__).resolve().parents[3] / "workbench").resolve(strict=True)
        if not (workbench / "salam_workbench/configurator_gui_bridge.py").is_file():
            raise ValueError("Selected workbench package is unavailable")
        command = [
            "wsl", "-d", distro, "--cd", self._checked_wsl_path(workbench, distro),
            "--exec", "/usr/bin/python3.8", "-B", "-m",
            "salam_workbench.configurator_gui_bridge", "prepare",
            "--engine", engine, "--benchmark", benchmark, "--config", config,
            "--distro", distro,
            "--requested-period", self.cycle_time_combo.currentText(),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
        if result.stderr:
            self.validation_output.append(result.stderr.strip()[-3000:])
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            raise ValueError("Bridge returned no structured receipt summary")
        summary = json.loads(lines[-1])
        if result.returncode != 0 or summary.get("state") != "prepared":
            summary["state"] = "failed"
            summary.setdefault("errors", []).append(
                "Bridge process returned " + str(result.returncode))
        return summary

'''


def render_checked_gui_source(source):
    """Replace only the old misleading generate route in a pinned GUI source."""
    if (
        not isinstance(source, str)
        or source.count("    def generate_files(self):") != 1
    ):
        raise ValueError("GUI generate action anchor changed")
    if source.count("    def save_config(self):") != 1:
        raise ValueError("GUI save action anchor changed")
    start = source.index("    def generate_files(self):")
    end = source.index("    def save_config(self):", start)
    old = source[start:end]
    if (
        "python3 -m salam_config.cli generate" not in old
        or "Generation completed successfully!" not in old
        or "QMessageBox.question" not in old
    ):
        raise ValueError("GUI old success route differs from reviewed source")
    label = 'self.generate_btn = QPushButton("Generate Files")'
    if source.count(label) != 1:
        raise ValueError("GUI Generate Files button label changed")
    result = source[:start] + _GUI_METHODS + source[end:]
    result = result.replace(
        label,
        'self.generate_btn = QPushButton("Prepare Selected YAML (checked)")\n'
        '        self.generate_btn.setToolTip("Uses existing on-disk YAML; unsaved form fields are not applied")',
        1,
    )
    ast.parse(result)
    return result


def install_gui_patch(original_gui, isolated_gui, evidence_dir, patch_path):
    """Patch the separate GUI copy, retain before-image and portable diff."""
    source = Path(original_gui).resolve(strict=True)
    target = Path(isolated_gui).resolve(strict=True)
    if (
        source == target
        or source.name != "config_generator.py"
        or target.name != source.name
    ):
        raise ValueError("Expected distinct original and independent GUI source files")
    if _sha(source) != ORIGINAL_GUI_SHA256 or _sha(target) != ORIGINAL_GUI_SHA256:
        raise ValueError("GUI source differs from reviewed baseline; refusing patch")
    evidence = Path(evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    record = {
        "schema_version": 1,
        "kind": "isolated_gui_checked_prepare_patch",
        "state": "planned",
        "original": str(source),
        "isolated": str(target),
        "original_sha256": _sha(source),
        "isolated_before_sha256": _sha(target),
    }
    _save(evidence / "gui-patch.json", record)
    try:
        before = target.read_text(encoding="utf-8")
        after = render_checked_gui_source(before)
        portable_diff = "".join(
            difflib.unified_diff(
                before.splitlines(True),
                after.splitlines(True),
                fromfile="a/gem5-SALAM-gui/src/gui/config_generator.py",
                tofile="b/gem5-SALAM-gui/src/gui/config_generator.py",
            )
        )
        before_path = evidence / "config_generator.py.before"
        shutil.copyfile(str(target), str(before_path))
        if _sha(before_path) != record["isolated_before_sha256"]:
            raise ValueError("GUI before-image copy differs")
        patch = Path(patch_path)
        patch.parent.mkdir(parents=True, exist_ok=True)
        patch.write_text(portable_diff, encoding="utf-8")
        temporary = target.with_name(target.name + ".workbench.writing")
        temporary.write_text(after, encoding="utf-8")
        ast.parse(temporary.read_text(encoding="utf-8"))
        temporary.replace(target)
        record.update(
            state="installed",
            isolated_after_sha256=_sha(target),
            before_image=str(before_path),
            before_image_sha256=_sha(before_path),
            portable_patch=str(patch),
            portable_patch_sha256=_sha(patch),
        )
        if _sha(source) != record["original_sha256"]:
            raise ValueError("Original GUI changed during isolated patch")
    except Exception as error:
        record["state"] = "failed"
        record["error"] = type(error).__name__ + ": " + str(error)
    _save(evidence / "gui-patch.json", record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare",))
    parser.add_argument("--engine", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--distro", required=True)
    parser.add_argument("--requested-period", required=True)
    parser.add_argument("--evidence-dir")
    args = parser.parse_args(argv)
    record = prepare_selected(
        args.engine,
        args.benchmark,
        args.config,
        distro=args.distro,
        requested_period=args.requested_period,
        evidence_dir=args.evidence_dir,
    )
    print(
        json.dumps(
            {
                "state": record["state"],
                "evidence_directory": record["evidence_directory"],
                "errors": record["errors"],
            }
        )
    )
    return 0 if record["state"] == "prepared" else 1


if __name__ == "__main__":
    raise SystemExit(main())
