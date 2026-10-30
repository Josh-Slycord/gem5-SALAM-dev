"""Install the checked GUI import hook with a saved before-image."""
import argparse
import ast
import datetime
import json
import shutil
from pathlib import Path

from .runner import file_hash

GUI_RELATIVE = Path("gem5-SALAM-gui/src/gui/config_generator.py")
OLD_MARKER = (
    "# Workbench editor adapter for the independent configurator-engine copy only."
)
NEW_MARKER = "# SALAM Research Workbench editor adapter (portable)."
HOOK = """\n\n# SALAM Research Workbench editor adapter (portable).
def _install_salam_workbench_editor():
    import os
    import sys
    from pathlib import Path
    _engine = Path(__file__).resolve().parents[3]
    _explicit = os.environ.get("SALAM_WORKBENCH_ROOT")
    _workbench = (Path(_explicit).resolve(strict=True) if _explicit
                  else _engine / "workbench")
    if not (_workbench / "salam_workbench/gui_editor_qt.py").is_file():
        if _explicit:
            raise RuntimeError("SALAM_WORKBENCH_ROOT has no checked editor package")
        return
    if str(_workbench) not in sys.path:
        sys.path.insert(0, str(_workbench))
    from salam_workbench.gui_editor_qt import install_editor
    ConfigGeneratorDialog._gui_source_path = __file__
    install_editor(ConfigGeneratorDialog)

_install_salam_workbench_editor()
"""


def render_hook(source):
    if source.count(NEW_MARKER) == 1 and source.endswith(HOOK):
        return source
    if NEW_MARKER in source:
        raise ValueError(
            "Existing portable GUI hook differs from reviewed implementation"
        )
    if OLD_MARKER in source:
        if source.count(OLD_MARKER) != 1:
            raise ValueError("Multiple legacy GUI hooks")
        source = source[: source.index(OLD_MARKER)].rstrip()
    if "class ConfigGeneratorDialog" not in source:
        raise ValueError("Expected SALAM GUI dialog class")
    result = source + HOOK
    ast.parse(result)
    return result


def install_hook(engine_root, evidence_dir):
    engine = Path(engine_root).resolve(strict=True)
    source = (engine / GUI_RELATIVE).resolve(strict=True)
    source.relative_to(engine)
    if (
        not (engine / "SConstruct").is_file()
        or not source.is_file()
        or source.is_symlink()
    ):
        raise ValueError("Expected simulator engine and regular GUI source")
    evidence = Path(evidence_dir).resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    before = source.read_bytes()
    before_hash = file_hash(source)
    record = {
        "schema_version": 1,
        "kind": "portable_gui_hook",
        "state": "planned",
        "engine": str(engine),
        "source": str(source),
        "before_sha256": before_hash,
        "recorded_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    (evidence / "gui-hook.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    try:
        text = before.decode("utf-8")
        after = render_hook(text)
        if after == text:
            record["state"] = "already_installed"
        else:
            before_path = evidence / "config_generator.py.before"
            shutil.copyfile(str(source), str(before_path))
            if file_hash(before_path) != before_hash:
                raise ValueError("GUI before-image differs from selected source")
            temporary = source.with_name(source.name + ".workbench.writing")
            temporary.write_text(after, encoding="utf-8")
            ast.parse(temporary.read_text(encoding="utf-8"))
            temporary.replace(source)
            record["state"] = "installed"
            record["before_image"] = str(before_path)
            record["before_image_sha256"] = before_hash
        record["after_sha256"] = file_hash(source)
    except Exception as error:
        record["state"] = "failed"
        record["errors"] = [type(error).__name__ + ": " + str(error)]
    (evidence / "gui-hook.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--evidence-dir", required=True)
    args = parser.parse_args(argv)
    result = install_hook(args.engine, args.evidence_dir)
    print(json.dumps(result))
    return 0 if result["state"] in ("installed", "already_installed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
