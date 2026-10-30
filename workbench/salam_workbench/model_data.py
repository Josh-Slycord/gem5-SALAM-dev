"""Read-only, provenance-bearing lookups of recovered model coefficients.

These are repository model values, not measured run power, energy, or area.
No engine modules are imported and no timing/profile fallback is performed.
"""
import argparse
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import yaml

ASSET = "salam_config/data/power_model_40nm.yaml"
UNITS = {"power": "mW", "energy": "pJ", "time": "ns", "area": "um^2"}
FIELD_UNITS = {
    "int_power": "mW", "switch_power": "mW", "dyn_power": "mW",
    "dyn_energy": "pJ", "leak_power": "mW", "area": "um^2",
    "critical_path": "ns",
}
REQUIRED_FIELDS = set(FIELD_UNITS) - {"critical_path"}
LIMITATIONS = [
    "Source characterization claim is unverified; synthesis reports and operating conditions were not found in the audited model folders.",
    "Coefficients do not measure this run and do not establish instantiated functional-unit count or utilization.",
    "Energy integration interval is unspecified; no power-times-period or operation-count aggregation is performed.",
    "No whole-accelerator, memory, interconnect, clock-tree, or system total is estimated.",
    "Instruction mapping is the model asset's mapping, not evidence of runtime resource allocation.",
]


class ModelDataError(ValueError):
    pass


class _UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key == "<<" or key in result:
            raise ModelDataError("line %d: duplicate, non-string, or merge key is unsupported" %
                                 (key_node.start_mark.line + 1))
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def convert_to_si(value, unit):
    """Convert one coefficient's declared unit; never combine coefficients."""
    factors = {"mW": ("0.001", "W"), "pJ": ("1e-12", "J"),
               "ns": ("1e-9", "s"), "um^2": ("1e-12", "m^2")}
    if not _number(value) or unit not in factors:
        raise ModelDataError("expected finite nonnegative coefficient and supported declared unit")
    factor, si_unit = factors[unit]
    # A decimal string avoids losing the original decimal precision during scaling.
    return {"value_decimal": str(Decimal(str(value)) * Decimal(factor)), "unit": si_unit}


def _base(asset):
    return {"schema_version": 1, "kind": "model_coefficients",
            "status": "available", "asset": asset,
            "characterization_verified": False,
            "source_confidence": "repository_claim_unverified",
            "limitations": list(LIMITATIONS)}


def _row(data, period):
    if not isinstance(data, dict):
        raise ModelDataError("timing row must be a mapping")
    coefficients = {}
    warnings = []
    for name, unit in FIELD_UNITS.items():
        value = data.get(name)
        if not _number(value):
            coefficients[name] = {"status": "unknown", "value": None, "unit": unit,
                                  "reason": "missing" if name not in data else "invalid coefficient",
                                  "source_value_repr": repr(value) if name in data else None}
        else:
            coefficients[name] = {"status": "available", "value": value, "unit": unit,
                                  "si": convert_to_si(value, unit)}
    complete = all(coefficients[k]["status"] == "available" for k in REQUIRED_FIELDS)
    if all(_number(data.get(k)) for k in ("int_power", "switch_power", "dyn_power")):
        if not math.isclose(data["dyn_power"], data["int_power"] + data["switch_power"],
                            rel_tol=0.0001, abs_tol=0.00001):
            warnings.append("Source dyn_power differs numerically from int_power + switch_power; original coefficients retained, component aggregation is not justified.")
    if all(_number(data.get(k)) for k in ("dyn_power", "dyn_energy")):
        if not math.isclose(data["dyn_energy"], data["dyn_power"] * period,
                            rel_tol=0.0001, abs_tol=0.00001):
            warnings.append("Source dyn_energy differs numerically from dyn_power times row period; the energy integration interval is unspecified, so this is not a correction or a validation failure.")
    extra = sorted(set(data) - set(FIELD_UNITS))
    if extra:
        warnings.append("Unsupported extra coefficient fields were not interpreted: " + ", ".join(extra))
    return {"status": "available" if complete else "unknown",
            "meaning": "source-declared per-unit model coefficients; not execution estimates",
            "cycle_time_ns": period, "coefficients": coefficients, "warnings": warnings}


def load_model_inventory(engine_root):
    """Return all source rows with SHA-256, declared metadata, and row caveats.

    Missing asset is unknown. Malformed metadata, units, keys, or mappings raise
    ModelDataError. Missing/invalid individual coefficients stay unknown.
    """
    root = Path(engine_root).resolve()
    path = root / ASSET
    asset = {"relative_path": ASSET, "sha256": None, "size_bytes": None}
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except FileNotFoundError:
        result = _base(asset)
        result.update(status="unknown", reason="model asset is absent", functional_units={},
                      instruction_mapping={}, declared_model=None)
        return result
    except (OSError, ValueError) as error:
        raise ModelDataError("model asset must be a readable file inside engine_root: " + str(error))
    try:
        if not resolved.is_file() or resolved.stat().st_size > 2 * 1024 * 1024:
            raise ModelDataError("model asset must be a regular file smaller than 2 MiB")
        raw = resolved.read_bytes()
        data = yaml.load(raw, Loader=_UniqueLoader)
    except (OSError, yaml.YAMLError) as error:
        raise ModelDataError("cannot read model asset: " + str(error))
    asset.update(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))
    if not isinstance(data, dict) or not isinstance(data.get("metadata"), dict):
        raise ModelDataError("model metadata mapping is required")
    metadata = data["metadata"]
    if metadata.get("units") != UNITS:
        raise ModelDataError("model units must explicitly be power=mW, energy=pJ, time=ns, area=um^2")
    for field in ("technology_node", "source"):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ModelDataError("metadata." + field + " must be explicitly declared")
    if metadata["technology_node"] != "40nm":
        raise ModelDataError("this adapter supports only the recovered 40nm asset schema")
    supported = metadata.get("supported_cycle_times")
    if (not isinstance(supported, list) or not supported or
            any(type(p) is not int or p <= 0 for p in supported) or len(set(supported)) != len(supported)):
        raise ModelDataError("supported_cycle_times must be distinct positive integer nanoseconds")
    fus, mapping = data.get("functional_units"), data.get("instruction_mapping")
    if not isinstance(fus, dict) or not fus or not isinstance(mapping, dict):
        raise ModelDataError("functional_units and instruction_mapping mappings are required")
    result = _base(asset)
    result["declared_model"] = {"technology_node": metadata["technology_node"],
                                "source_claim": metadata["source"], "units": dict(UNITS),
                                "supported_cycle_times_ns": list(supported),
                                "voltage": None, "temperature": None,
                                "process_corner": None, "activity_factor": None,
                                "characterization_tool_version": None}
    result["functional_units"] = {}
    for name, fu in fus.items():
        if not isinstance(fu, dict) or not isinstance(fu.get("timing"), dict):
            raise ModelDataError("functional unit " + name + " must have timing rows")
        if not isinstance(fu.get("description"), str):
            raise ModelDataError(name + ".description must be a string")
        for field in ("enum_value", "default_cycles"):
            if type(fu.get(field)) is not int or fu[field] < 0:
                raise ModelDataError(name + "." + field + " must be an explicit nonnegative integer")
        if "per_bit" in fu and type(fu["per_bit"]) is not bool:
            raise ModelDataError(name + ".per_bit must be boolean when provided")
        # Missing per_bit is not silently interpreted as a known physical width.
        scope = "per_bit" if fu.get("per_bit") is True else "per_functional_unit_as_declared"
        record = {"description": fu.get("description"), "enum_value": fu.get("enum_value"),
                  "default_cycles": fu.get("default_cycles"), "scope": scope,
                  "per_bit_declared": fu.get("per_bit"), "timing": {}}
        for label, row in fu["timing"].items():
            if not re.fullmatch(r"[1-9][0-9]*ns", label):
                raise ModelDataError(name + ": timing key must be exact positive integer ns")
            period = int(label[:-2])
            if period not in supported:
                raise ModelDataError(name + ": row period is absent from declared supported periods")
            record["timing"][label] = _row(row, period)
        result["functional_units"][name] = record
    for instruction, fu in mapping.items():
        if not isinstance(fu, str) or fu not in fus:
            raise ModelDataError("instruction mapping has an unknown functional unit: " + instruction)
    result["instruction_mapping"] = dict(mapping)
    result["counts"] = {"functional_units": len(fus), "instruction_mappings": len(mapping),
                         "timing_rows": sum(len(f["timing"]) for f in result["functional_units"].values())}
    return result


def model_estimate(engine_root, *, cycle_time_ns, instruction=None, functional_unit=None):
    """Lookup exactly one FU/period; unknown inputs never fall back to a profile."""
    selectors = [v for v in (instruction, functional_unit) if v is not None]
    if len(selectors) != 1 or not isinstance(selectors[0], str) or not selectors[0]:
        raise ModelDataError("provide exactly one nonempty instruction or functional_unit name")
    if not _number(cycle_time_ns) or cycle_time_ns == 0:
        raise ModelDataError("cycle_time_ns must be a finite positive number")
    inventory = load_model_inventory(engine_root)
    result = {k: inventory[k] for k in ("schema_version", "kind", "asset",
              "characterization_verified", "source_confidence", "limitations", "declared_model")}
    result.update(status="unknown", instruction=instruction, functional_unit=functional_unit,
                  cycle_time_ns=cycle_time_ns, coefficients=None, warnings=[])
    if inventory["status"] != "available":
        result["reason"] = inventory["reason"]
        return result
    name = functional_unit if functional_unit is not None else inventory["instruction_mapping"].get(instruction)
    result["functional_unit"] = name
    if name not in inventory["functional_units"]:
        result["reason"] = "functional unit or instruction is not in the model asset"
        return result
    fu = inventory["functional_units"][name]
    period = Decimal(str(cycle_time_ns))
    label = str(int(period)) + "ns" if period == period.to_integral_value() else None
    row = fu["timing"].get(label)
    result.update(scope=fu["scope"], per_bit_declared=fu["per_bit_declared"],
                  description=fu["description"], enum_value=fu["enum_value"],
                  model_default_cycles=fu["default_cycles"])
    if row is None:
        result["reason"] = "exact period row is absent; no fallback or interpolation permitted"
        return result
    result.update(row)
    if row["status"] == "unknown":
        result["reason"] = "one or more required source coefficients are missing or invalid"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path, required=True)
    selectors = parser.add_mutually_exclusive_group()
    selectors.add_argument("--instruction")
    selectors.add_argument("--functional-unit")
    parser.add_argument("--cycle-time-ns", type=float)
    args = parser.parse_args(argv)
    try:
        if args.instruction or args.functional_unit:
            result = model_estimate(args.engine_root, instruction=args.instruction,
                                    functional_unit=args.functional_unit,
                                    cycle_time_ns=args.cycle_time_ns)
        else:
            if args.cycle_time_ns is not None:
                parser.error("--cycle-time-ns needs a selector")
            result = load_model_inventory(args.engine_root)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result["status"] == "available" else 1
    except ModelDataError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
