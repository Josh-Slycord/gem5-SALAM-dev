"""Loaded by generated gem5 scripts, before m5.instantiate().

This module deliberately depends only on each live SimObject's parameter table.
The separate host-side witness compares its normalized requests with config.ini.
"""
import json
import re
from pathlib import Path


def configure_system(system, request_path):
    request = json.loads(Path(request_path).read_text())
    records = []
    if request.get("result_file_transport") is not None:
        if request["result_file_transport"] != "gem5_semihosting_writefile_text_v1":
            raise ValueError("Unknown benchmark output transport")
        from m5.objects import ArmSemihosting

        system.semihosting = ArmSemihosting()
        records.append(
            {
                "section": "system",
                "parameter": "semihosting",
                "requested": "ArmSemihosting",
                "normalized": "system.semihosting",
                "compiled_type": "ArmSemihosting",
            }
        )
    for section, parameters in request["parameters"].items():
        parts = section.split(".")
        if parts[0] != "system" or any(
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", p) for p in parts
        ):
            raise ValueError("Invalid SimObject section: " + section)
        obj = system
        for name in parts[1:]:
            obj = getattr(obj, name)
        for name, value in parameters.items():
            if name not in obj._params or name.startswith("_"):
                raise ValueError("Unknown compiled parameter: " + section + "." + name)
            descriptor = obj._params[name]
            # Structural object replacement belongs to topology generation.
            if (
                hasattr(descriptor.ptype, "_params")
                or type(descriptor).__name__ == "VectorParamDesc"
            ):
                raise ValueError(
                    "Only scalar value parameters can be overridden: "
                    + section
                    + "."
                    + name
                )
            setattr(obj, name, value)  # gem5 performs actual parameter conversion.
            converted = getattr(obj, name)
            integer_type = re.fullmatch(
                r"(?:U?Int\d*|Unsigned|Counter|Tick|Cycles)",
                descriptor.ptype_str,
            )
            if isinstance(value, float) and integer_type and not value.is_integer():
                raise ValueError(
                    "Compiled integer parameter would truncate a fraction: "
                    + section
                    + "."
                    + name
                )
            normalized = converted.ini_str()
            records.append(
                {
                    "section": section,
                    "parameter": name,
                    "requested": value,
                    "normalized": normalized,
                    "compiled_type": descriptor.ptype_str,
                }
            )
    Path(request["witness_path"]).write_text(
        json.dumps(
            {"state": "applied_before_instantiation", "parameters": records},
            indent=2,
        )
        + "\n"
    )
    if request.get("system_witness_path"):
        from workbench_system_witness import capture_system

        Path(request["system_witness_path"]).write_text(
            json.dumps(
                capture_system(system, request.get("system_options", {})),
                indent=2,
            )
            + "\n"
        )
