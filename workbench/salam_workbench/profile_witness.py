"""Witness generated functional-unit defaults against gem5 config.ini.

This checks parameter transport, not model calibration or measured energy.
"""
import ast
import configparser
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path

FLOAT_FIELDS = ("internal_power", "switch_power", "dynamic_power",
                "dynamic_energy", "leakage_power", "area", "path_delay")
UNIT_FIELDS = ("power_units", "energy_units", "time_units", "area_units")
FIELDS = UNIT_FIELDS + ("fu_latency",) + FLOAT_FIELDS
NUMERIC = FLOAT_FIELDS + ("fu_latency",)
REGISTRY = Path("configs/SALAM/HWAccConfig.py")
DEFAULTS = Path("src/hwacc/FunctionalUnits.py")
MARKER = ".hw_interface.functional_units."


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _registry(source):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_FU_REGISTRY"
                for t in node.targets):
            if not isinstance(node.value, ast.Dict):
                raise ValueError("_FU_REGISTRY must be a literal dictionary")
            items = {}
            for key, value in zip(node.value.keys, node.value.values):
                name = ast.literal_eval(key)
                if not isinstance(name, str) or not isinstance(value, ast.Name):
                    raise ValueError("Nonliteral functional-unit registry entry")
                if name in items:
                    raise ValueError("Duplicate functional-unit registry entry")
                items[name] = value.id
            if not items:
                raise ValueError("Empty functional-unit registry")
            return items
    raise ValueError("Missing _FU_REGISTRY")


def _defaults(source, names):
    classes = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.ClassDef) or node.name not in names:
            continue
        if node.name in classes:
            raise ValueError("Duplicate generated class: " + node.name)
        fields = {}
        for statement in node.body:
            if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
                continue
            target, call = statement.targets[0], statement.value
            if (not isinstance(target, ast.Name) or target.id not in FIELDS or
                    not isinstance(call, ast.Call) or not call.args or
                    not isinstance(call.func, ast.Attribute) or
                    not isinstance(call.func.value, ast.Name) or
                    call.func.value.id != "Param"):
                continue
            literal = ast.get_source_segment(source, call.args[0])
            value = ast.literal_eval(call.args[0])
            if target.id in NUMERIC:
                value = Decimal(literal)
            elif not isinstance(value, str):
                raise ValueError("Nonstring unit: " + target.id)
            if target.id in fields:
                raise ValueError("Duplicate generated field: " + target.id)
            fields[target.id] = (value, literal, call.func.attr)
        classes[node.name] = fields
    if names - classes.keys():
        raise ValueError("Missing generated classes: " +
                         ", ".join(sorted(names - classes.keys())))
    return classes


def _same(field, expected, observed):
    if field not in NUMERIC:
        return str(expected) == str(observed)
    try:
        actual, wanted = Decimal(str(observed)), Decimal(str(expected))
    except InvalidOperation:
        return False
    if not actual.is_finite() or not wanted.is_finite():
        return False
    return abs(actual - wanted) <= max(Decimal("1e-12"),
                                      abs(wanted) * Decimal("1e-6"))


def _plain(value):
    return str(value) if isinstance(value, Decimal) else value


def witness_profiles(engine_root, config_ini, *, parameter_overrides=None):
    """Return JSON-safe transport checks for each accelerator and FU field.

    parameter_overrides maps exact config.ini section names to field/value maps.
    Engine Python is parsed as source; it is never imported or executed.
    """
    root, ini = Path(engine_root), Path(config_ini)
    result = {"state": "failed", "checks": [], "issues": [], "source_hashes": {},
              "model_claims": {"coefficient_transport_verified": False,
                               "calibration_verified": None,
                               "measured_power_or_energy": False,
                               "scope": "generated SimObject defaults versus config.ini"}}
    overrides = parameter_overrides or {}
    if not isinstance(overrides, dict):
        result["issues"].append({"kind": "invalid_overrides"})
        return result
    for relative in (REGISTRY, DEFAULTS):
        path = root / relative
        if not path.is_file():
            result["issues"].append({"kind": "missing_source", "path": str(path)})
            return result
        result["source_hashes"][relative.as_posix()] = _sha(path)
    if not ini.is_file():
        result["issues"].append({"kind": "missing_config_ini", "path": str(ini)})
        return result
    result["source_hashes"]["config.ini"] = _sha(ini)
    try:
        registry = _registry((root / REGISTRY).read_text(encoding="utf-8"))
        defaults = _defaults((root / DEFAULTS).read_text(encoding="utf-8"),
                             set(registry.values()))
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.optionxform = str
        with ini.open(encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, UnicodeError, SyntaxError, ValueError,
            configparser.Error) as error:
        result["issues"].append({"kind": "parse_error", "detail": str(error)})
        return result
    groups = {}
    for section in parser.sections():
        if MARKER in section and section.startswith("system."):
            accelerator, name = section.rsplit(MARKER, 1)
            if accelerator and name and "." not in name:
                groups.setdefault(accelerator, {})[name] = section
    if not groups:
        result["issues"].append({"kind": "no_functional_units"})
        return result
    for accelerator, sections in sorted(groups.items()):
        for name in sorted(sections.keys() - registry.keys()):
            result["issues"].append({"kind": "unknown_functional_unit",
                                     "section": sections[name]})
        for name, class_name in registry.items():
            section = sections.get(name)
            if section is None:
                result["issues"].append({"kind": "missing_functional_unit",
                                         "accelerator": accelerator,
                                         "functional_unit": name})
                continue
            declared = overrides.get(section, {})
            if not isinstance(declared, dict):
                result["issues"].append({"kind": "invalid_section_overrides",
                                         "section": section})
                continue
            for field in FIELDS:
                source = defaults[class_name].get(field)
                if source is None:
                    result["issues"].append({"kind": "missing_source_default",
                                             "section": section, "field": field})
                    continue
                default, literal, param_type = source
                explicit = field in declared
                expected = declared[field] if explicit else default
                origin = ("explicit_parameter_override" if explicit
                          else "generated_source_default")
                present = parser.has_option(section, field)
                actual = parser.get(section, field) if present else None
                passed = present and _same(field, expected, actual)
                result["checks"].append({
                    "accelerator": accelerator, "section": section,
                    "functional_unit": name, "class": class_name, "field": field,
                    "expected": _plain(expected), "observed": actual,
                    "origin": origin, "source_default": _plain(default),
                    "source_literal": literal, "source_param_type": param_type,
                    "status": "passed" if passed else "failed"})
                if not passed:
                    result["issues"].append({
                        "kind": "missing_profile_field" if not present
                                else "profile_mismatch",
                        "section": section, "field": field,
                        "expected": _plain(expected), "observed": actual,
                        "origin": origin})
                if (field in FLOAT_FIELDS and
                        param_type in ("UInt32", "UInt64", "Int32", "Int64") and
                        default != default.to_integral_value()):
                    result["issues"].append({
                        "kind": "lossy_source_param_type", "section": section,
                        "field": field, "param_type": param_type,
                        "source_default": _plain(default)})
    result["state"] = "passed" if not result["issues"] else "failed"
    result["model_claims"]["coefficient_transport_verified"] = (
        result["state"] == "passed")
    return result
