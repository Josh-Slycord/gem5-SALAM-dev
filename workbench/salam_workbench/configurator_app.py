"""Launch the checked SALAM editor against its independent configured engine."""
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
    parser.add_argument("--benchmark", default="gemm")
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
    from PySide6.QtWidgets import QApplication, QWidget

    if (
        ConfigGeneratorDialog.generate_files.__module__
        != "salam_workbench.gui_editor_qt"
    ):
        raise ValueError(
            "The independent GUI does not have the checked editor adapter installed"
        )
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.wsl_status = type(
        "SelectedDistribution",
        (),
        {"get_selected_distro": lambda self: selected["distribution"]},
    )()
    dialog = ConfigGeneratorDialog(engine, parent)
    index = dialog.benchmark_combo.findData(args.benchmark)
    if index < 0:
        raise ValueError("Selected benchmark is not present in the GUI catalog")
    dialog.benchmark_combo.setCurrentIndex(index)
    if dialog._base_document is None:
        raise ValueError("Selected configuration could not be loaded into the editor")
    if args.inspect:
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
        }
        print(json.dumps(result))
        dialog.close()
        parent.close()
        return 0
    dialog.setWindowTitle("SALAM Research Workbench — configuration editor")
    dialog.resize(1400, 1000)
    dialog.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(launch())
