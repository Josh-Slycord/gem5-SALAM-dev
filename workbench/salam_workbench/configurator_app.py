"""Launch the integrated SALAM desktop workbench against its checked engines."""
import argparse
import json
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def launch(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Build the actual widgets offscreen and report readiness",
    )
    parser.add_argument("--benchmark", default=None)
    args = parser.parse_args(argv)
    if args.inspect:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    manifest = json.loads((PROJECT / "workspace.json").read_text(encoding="utf-8-sig"))
    selected = manifest["configuration_engine"]
    engine = Path(selected["path"]).resolve(strict=True)
    gui = engine / "gem5-SALAM-gui/src"
    os.environ["SALAM_WORKBENCH_ROOT"] = str(PROJECT)
    sys.path.insert(0, str(gui))
    from gui.config_generator import ConfigGeneratorDialog
    from PySide6.QtWidgets import QApplication

    from .workbench_window import WorkbenchWindow

    if (
        ConfigGeneratorDialog.generate_files.__module__
        != "salam_workbench.gui_editor_qt"
    ):
        raise ValueError(
            "The independent GUI does not have the checked editor adapter installed"
        )
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    window = WorkbenchWindow(
        PROJECT,
        engine,
        selected["distribution"],
        ConfigGeneratorDialog,
        args.benchmark,
        auto_discover=not args.inspect,
    )
    if args.inspect:
        from .workbench_catalog import discover_benchmarks

        window._preferred_benchmark = args.benchmark or "benchmarks/sys_validation/gemm"
        window.catalog = discover_benchmarks(engine)
        window._show_catalog()
        dialog = window.editor
        request = dialog._make_request()
        result = {
            "state": "ready",
            "engine": str(engine),
            "distribution": selected["distribution"],
            "benchmark": request["benchmark"],
            "action": request["action"],
            "button": dialog.generate_btn.text(),
            "asynchronous_backend": True,
            "source_yaml_written": False,
            "simulation_started": False,
            "component_count": dialog.component_tree.topLevelItemCount(),
            "instruction_count": dialog.inst_tree.topLevelItemCount(),
            "workbench_tabs": [
                window.pages.tabText(i) for i in range(window.pages.count())
            ],
            "catalog_count": len(window.catalog),
            "configurable_benchmarks": sum(
                bool(item["can_configure"]) for item in window.catalog
            ),
            "configured_run_candidates": sum(
                bool(item["can_run"]) for item in window.catalog
            ),
            "reference_workloads": [
                item["key"]
                for item in window.catalog
                if item.get("fixed_dataset_check_available")
            ],
        }
        print(json.dumps(result))
        window.close()
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(launch())
