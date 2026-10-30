"""Pure, source-bound import of legacy GUI configuration syntax.

The importer changes an in-memory YAML document only. It does not erase fields
the current runtime ignores; the strict configuration contract checks those.
"""

import ast
from pathlib import Path

import yaml

from .config_contract import _Loader, _params, _registry, _sha


_ALIASES = {"and": "and_inst", "or": "or_inst", "xor": "xor_inst",
            "switch": "switch_inst"}


def import_configuration(config_path, engine_root):
    """Return canonical documents and an exact, reproducible edit inventory.

    Unknown symbols and collisions raise ``ValueError``. The caller decides
    where to write the returned documents and must retain the original bytes.
    ``functional_unit`` integers and unrelated fields are preserved as given.
    """
    path = Path(config_path).resolve(strict=True)
    engine = Path(engine_root).resolve(strict=True)
    registry_path = engine / "configs/SALAM/HWAccConfig.py"
    fu_path = engine / "src/hwacc/FunctionalUnits.py"
    if not registry_path.is_file() or not fu_path.is_file():
        raise ValueError("Runtime registry or generated FU SimObject source missing")
    registry_tree = ast.parse(registry_path.read_text(encoding="utf-8"))
    fu_tree = ast.parse(fu_path.read_text(encoding="utf-8"))
    instruction_names = _registry(registry_tree, "_INST_REGISTRY")
    fu_names = _registry(registry_tree, "_FU_REGISTRY")
    ids = {name: _params(fu_tree, class_name).get("enum_value")
           for name, class_name in fu_names.items()}
    if not ids or any(type(value) is not int or value < 0 for value in ids.values()):
        raise ValueError("Generated FU identifiers are incomplete")
    try:
        documents = list(yaml.load_all(path.read_text(encoding="utf-8"), Loader=_Loader))
    except (yaml.YAMLError, ValueError) as error:
        raise ValueError("Invalid legacy GUI YAML: " + str(error)) from error
    if not documents:
        raise ValueError("Legacy GUI YAML has no documents")
    changes = []
    for di, document in enumerate(documents):
        if not isinstance(document, dict):
            raise ValueError("Document {} must be a mapping".format(di))
        hardware = document.get("hw_config", {})
        if not isinstance(hardware, dict):
            raise ValueError("Document {} hw_config must be a mapping".format(di))
        for accelerator, settings in hardware.items():
            if accelerator == "name" or settings is None:
                continue
            if not isinstance(settings, dict):
                raise ValueError("hw_config.{} must be a mapping".format(accelerator))
            instructions = settings.get("instructions", {})
            if not isinstance(instructions, dict):
                raise ValueError("hw_config.{}.instructions must be a mapping".format(accelerator))
            canonical = {}
            for old_name, fields in instructions.items():
                if not isinstance(old_name, str):
                    raise ValueError("Instruction name must be text")
                name = _ALIASES.get(old_name, old_name)
                if name not in instruction_names:
                    raise ValueError("Unknown instruction {} in hw_config.{}".format(old_name, accelerator))
                if name in canonical:
                    raise ValueError("Instruction alias collision at hw_config.{}.{}".format(accelerator, name))
                if not isinstance(fields, dict):
                    raise ValueError("hw_config.{}.instructions.{} must be a mapping".format(accelerator, old_name))
                converted = dict(fields)
                if old_name != name:
                    changes.append({"path": [di, "hw_config", accelerator, "instructions", old_name],
                                    "field": "instruction_name", "before": old_name, "after": name,
                                    "reason": "runtime_instruction_registry_name"})
                value = converted.get("functional_unit")
                if isinstance(value, str):
                    if value not in ids:
                        raise ValueError("Unknown symbolic functional unit {} in hw_config.{}.{}".format(
                            value, accelerator, old_name))
                    converted["functional_unit"] = ids[value]
                    changes.append({"path": [di, "hw_config", accelerator, "instructions", name,
                                             "functional_unit"],
                                    "field": "functional_unit", "before": value, "after": ids[value],
                                    "reason": "generated_FU_enum_value"})
                canonical[name] = converted
            settings["instructions"] = canonical
    return {"schema_version": 1, "kind": "salam_legacy_gui_import",
            "documents": documents, "transformations": changes,
            "source": {"path": str(path), "sha256": _sha(path)},
            "consumer_sources": {
                "configs/SALAM/HWAccConfig.py": _sha(registry_path),
                "src/hwacc/FunctionalUnits.py": _sha(fu_path)},
            "scope": "In-memory syntax conversion only; no generation, build, simulation, or power calibration"}
