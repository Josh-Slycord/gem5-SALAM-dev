"""Derived-data controls: corrupt one output, retain guest pass and valid hashes.

No simulator rerun is represented by this script. Original runs remain intact.
The production result reader and actual results widgets must reject the copied
output on numerical grounds even when its refreshed transport hash is valid.
"""
import argparse
import copy
import hashlib
import json
import os
import shutil
import struct
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
os.environ["SALAM_WORKBENCH_ROOT"] = str(PROJECT)
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from salam_workbench.benchmark_validation import numerical_output_relative
from salam_workbench.checks import source_identity
from salam_workbench.workbench_results import load_run
from salam_workbench.workbench_window import WorkbenchWindow


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    args.acceptance = args.acceptance.resolve(strict=True)
    args.evidence_dir = args.evidence_dir.absolute()
    args.evidence_dir.relative_to((PROJECT / "evidence").resolve(strict=True))
    args.evidence_dir.mkdir(parents=True, exist_ok=False)
    accepted = json.loads(args.acceptance.read_text())
    assert accepted["state"] == "passed"
    before_source = source_identity(PROJECT)["sha256"]
    manifest = json.loads((PROJECT / "workspace.json").read_text(encoding="utf-8-sig"))
    selected = manifest["configuration_engine"]
    engine = Path(selected["path"]).resolve(strict=True)
    sys.path.insert(0, str(engine / "gem5-SALAM-gui/src"))
    from gui.config_generator import ConfigGeneratorDialog

    app = QApplication.instance() or QApplication([])
    settings = QSettings(
        str(args.evidence_dir / "test-preferences.ini"), QSettings.IniFormat
    )
    window = WorkbenchWindow(
        PROJECT,
        engine,
        selected["distribution"],
        ConfigGeneratorDialog,
        settings=settings,
        auto_discover=False,
    )
    window.show()
    deadline = time.monotonic() + 60
    while window._busy or window._tasks or getattr(window, "_task_queue", {}):
        app.processEvents()
        assert time.monotonic() < deadline, "Initial background reads did not finish"
        time.sleep(0.02)
    rows = []
    for case in accepted["cases"]:
        workload = Path(case["benchmark"]).name
        assert workload in ("fft", "stencil3d") and case["state"] == "passed"
        original_gui = Path(case["evidence_directory"]) / "gui-execution.json"
        gui = json.loads(original_gui.read_text())
        pipeline_path = Path(gui["pipeline_receipt"]["path"])
        pipeline = json.loads(pipeline_path.read_text())
        original_run = Path(pipeline["run_directory"])
        relative = numerical_output_relative(pipeline)
        original_output = original_run / relative
        original_hashes = {
            str(p): digest(p)
            for p in (
                original_gui,
                pipeline_path,
                original_run / "run.json",
                original_output,
            )
        }
        target = args.evidence_dir / workload
        target.mkdir()
        control_run = target / "run"
        assert not any(p.is_symlink() for p in original_run.rglob("*"))
        shutil.copytree(str(original_run), str(control_run))
        output = control_run / relative
        lines = output.read_text().splitlines()
        changed = False
        for index, line in enumerate(lines):
            if line.startswith("SALAM_RESULT 0 "):
                prefix, number, value = line.split()
                if workload == "fft":
                    old = struct.unpack(">d", bytes.fromhex(value[:16]))[0]
                    value = struct.pack(">d", old + 12345.0).hex() + value[16:]
                else:
                    value = "%08x" % (int(value, 16) ^ 1)
                lines[index] = "%s %s %s" % (prefix, number, value)
                changed = True
                break
        assert changed
        output.write_text("\n".join(lines) + "\n")
        raw_path = control_run / "run.json"
        raw = json.loads(raw_path.read_text())
        entries = [a for a in raw["artifacts"] if a["path"] == relative]
        assert len(entries) == 1
        entries[0]["sha256"] = digest(output)
        if "bytes" in entries[0]:
            entries[0]["bytes"] = output.stat().st_size
        save(raw_path, raw)
        derived = copy.deepcopy(pipeline)
        derived["run_directory"] = str(control_run)
        derived["evidence_directory"] = str(target)
        save(target / "configuration.json", derived)
        result = load_run(target / "configuration.json", PROJECT)
        checks = {row["name"]: row for row in result["checks"]}
        numerical = checks["Independent numerical validation"]
        failures = [c["name"] for c in result["checks"] if c["status"] == "failed"]
        artifact = next(a for a in result["artifacts"] if a["path"] == str(output))
        assert result["state"] == "passed" and result["validation_state"] == "failed"
        assert checks["Guest numerical checker"]["status"] == "passed"
        assert checks["Simulator exit"]["status"] == "passed"
        assert artifact["status"] == "hash_verified"
        assert failures == ["Independent numerical validation"] and not result["errors"]
        assert result["independent_oracle"]["mismatch_count"] == 1
        assert (
            result["independent_oracle"]["compared_count"]
            == result["independent_oracle"]["expected_count"]
        )
        window._show_run(result)
        window.pages.setCurrentIndex(2)
        validation_tab = window.checks
        while (
            validation_tab is not None
            and window.result_tabs.indexOf(validation_tab) < 0
        ):
            validation_tab = validation_tab.parentWidget()
        if validation_tab is None:
            raise ValueError("Actual validation tab was not found")
        window.result_tabs.setCurrentWidget(validation_tab)
        app.processEvents()
        rendered = [
            [window.checks.topLevelItem(i).text(c) for c in range(4)]
            for i in range(window.checks.topLevelItemCount())
        ]
        assert any(
            row[0] == "Independent numerical validation" and row[1] == "failed"
            for row in rendered
        )
        assert "Evidence assessment: failed" in window.result_scope.text()
        assert window.grab().save(str(target / "rejected-output.png"))
        assert all(digest(path) == value for path, value in original_hashes.items())
        save(target / "reader-result.json", result)
        rows.append(
            {
                "workload": workload,
                "state": "passed",
                "scope": "Derived output corruption; no simulator rerun",
                "original_receipts_unchanged": True,
                "original_hashes": original_hashes,
                "guest_checker": checks["Guest numerical checker"]["status"],
                "transport_hash": artifact["status"],
                "independent_oracle": result["independent_oracle"],
                "failed_checks": failures,
                "rendered_checks": rendered,
                "displayed_assessment": window.result_scope.text(),
                "copied_control_directory": str(target),
            }
        )
        print(
            json.dumps(
                {
                    "workload": workload,
                    "state": "passed",
                    "guest_pass_retained": True,
                    "mismatches": 1,
                }
            ),
            flush=True,
        )
    assert len(rows) == 2
    after_source = source_identity(PROJECT)["sha256"]
    assert before_source == after_source
    record = {
        "kind": "gui_rebuilt_workload_independent_output_negative_controls",
        "state": "passed",
        "simulation_rerun": False,
        "scope": __doc__,
        "acceptance_source": {
            "path": str(args.acceptance),
            "sha256": digest(args.acceptance),
        },
        "source_sha256": before_source,
        "source_unchanged": True,
        "cases": rows,
    }
    save(args.evidence_dir / "controls.json", record)
    window.close()
    app.processEvents()
    print(json.dumps({"state": "passed", "evidence": str(args.evidence_dir)}))


if __name__ == "__main__":
    main()
