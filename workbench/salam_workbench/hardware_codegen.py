"""Isolated, evidence-bound use of the recovered SALAM hardware class generator.

Generation is not a simulator build or a proof that a model coefficient is
calibrated. This adapter never edits the source engine.
"""
import ast
import datetime
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

SCRIPT_FILES = (
    "HWProfileGenerator.py",
    "SALAMClassGenerator.py",
    "SALAMArgs.py",
)
FLOAT_FIELDS = (
    "internal_power",
    "switch_power",
    "dynamic_power",
    "dynamic_energy",
    "leakage_power",
    "area",
    "path_delay",
)
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


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


def _source(root, relative):
    path = root / relative
    if path.is_symlink():
        raise ValueError("Symlinked source is unsupported: " + str(relative))
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    if not resolved.is_file():
        raise ValueError("Expected a source file: " + str(relative))
    return resolved


def _copy_source(root, stage, relative, records):
    original = _source(root, relative)
    target = stage / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(original), str(target))
    digest = _sha(original)
    if _sha(target) != digest:
        raise ValueError("Staged source copy differs: " + str(relative))
    records.append(
        {
            "relative_path": relative.as_posix(),
            "source_sha256": digest,
            "staged_sha256": digest,
        }
    )
    return target


def _replace_once(text, original, replacement, label):
    if text.count(original) != 1:
        raise ValueError("Generator template changed: " + label)
    return text.replace(original, replacement, 1)


def _detect_generator_template(text):
    legacy = (
        "self.fu_list = os.listdir(self.yaml_dir)",
        "generate_hw_models = HWModel(benchname=benchmark_args.bench, latency='5ns')",
    )
    canonical = (
        "self.fu_list = sorted(os.listdir(self.yaml_dir))",
        "generate_hw_models = HWModel(benchname=benchmark_args.bench, "
        "model=benchmark_args.model, latency=benchmark_args.latency, profile=benchmark_args.profile)",
    )
    counts = tuple(text.count(token) for token in legacy + canonical)
    if counts == (1, 1, 0, 0):
        return "legacy"
    if counts == (0, 0, 1, 1):
        return "canonical"
    raise ValueError(
        "HWProfileGenerator template is neither recognized legacy nor canonical; "
        "selection and ordering templates must each occur exactly once"
    )


def _detect_class_template(text):
    uint32 = tuple(
        text.count(r"\t" + name + " = Param.UInt32(") for name in FLOAT_FIELDS
    )
    floating = tuple(
        text.count(r"\t" + name + " = Param.Float(") for name in FLOAT_FIELDS
    )
    legacy_limit = text.count(
        "self.inst_dict['instructions'][inst_name]['functional_unit_limit']"
    )
    canonical_limit = text.count(
        "self.inst_dict['instructions'][inst_name].get('functional_unit_limit', 0)"
    )
    if (
        all(count == 1 for count in uint32)
        and not any(floating)
        and (legacy_limit, canonical_limit) == (1, 0)
    ):
        return "legacy"
    if (
        all(count == 1 for count in floating)
        and not any(uint32)
        and (legacy_limit, canonical_limit) == (0, 1)
    ):
        return "canonical"
    raise ValueError(
        "SALAMClassGenerator template is neither recognized legacy nor canonical; "
        "parameter templates must each occur exactly once"
    )


def _patch(stage, filename, transform, patches):
    path = stage / filename
    before = path.read_text(encoding="utf-8")
    template_form = "unknown"
    if filename == "HWProfileGenerator.py":
        template_form = _detect_generator_template(before)
    elif filename == "SALAMClassGenerator.py":
        template_form = _detect_class_template(before)

    after = transform(before)
    if before == after:
        if template_form == "canonical":
            patches.append(
                {
                    "relative_path": filename,
                    "template_form": "canonical",
                    "source_sha256": hashlib.sha256(before.encode()).hexdigest(),
                    "patched_sha256": _sha(path),
                    "applied": False,
                    "unified_diff": "",
                }
            )
            return
        raise ValueError("No change to staged generator: " + filename)

    path.write_text(after, encoding="utf-8")
    patches.append(
        {
            "relative_path": filename,
            "template_form": template_form,
            "source_sha256": hashlib.sha256(before.encode()).hexdigest(),
            "patched_sha256": _sha(path),
            "applied": True,
            "unified_diff": "".join(
                difflib.unified_diff(
                    before.splitlines(True),
                    after.splitlines(True),
                    fromfile="source/" + filename,
                    tofile="staged/" + filename,
                )
            ),
        }
    )


def _profile_inputs(root, stage, benchmark, model, period, profile, records):
    base = (
        Path("benchmarks/sys_validation")
        / benchmark
        / "configs/hw_interface/functional_units"
        / model
        / period
        / profile
    )
    folder = (root / base).resolve(strict=True)
    folder.relative_to(root)
    if not folder.is_dir() or (root / base).is_symlink():
        raise ValueError("Hardware profile directory unavailable")
    units = sorted(path.name for path in folder.iterdir())
    if not units or any(
        not NAME.fullmatch(unit)
        or not (folder / unit).is_dir()
        or (folder / unit).is_symlink()
        for unit in units
    ):
        raise ValueError("Hardware profile must contain named unit directories")
    for unit in units:
        relative = base / unit / (unit + ".yml")
        copied = _copy_source(root, stage, relative, records)
        data = yaml.safe_load(copied.read_text(encoding="utf-8"))
        actual_alias = (
            data.get("functional_unit", {}).get("parameters", {}).get("alias")
        )
        if actual_alias != unit:
            raise ValueError("Profile alias disagrees with directory: " + unit)
    inst_relative = (
        Path("benchmarks/sys_validation")
        / benchmark
        / "configs/hw_interface/instructions/inst_list.yml"
    )
    inst_path = _copy_source(root, stage, inst_relative, records)
    instructions = yaml.safe_load(inst_path.read_text(encoding="utf-8"))
    names = instructions.get("instructions") if isinstance(instructions, dict) else None
    if (
        not isinstance(names, dict)
        or not names
        or any(not NAME.fullmatch(name) for name in names)
    ):
        raise ValueError("Instruction list is missing or malformed")
    return units, sorted(names), inst_relative


def _expected_outputs(units, instructions):
    base = Path("src/hwacc")
    fu = base / "HWModeling/generated/functionalunits"
    ins = base / "HWModeling/generated/instructions"
    outputs = [
        base / "FunctionalUnits.py",
        base / "InstConfig.py",
        base / "HWModeling/src/functional_units.hh",
        base / "HWModeling/src/instruction_config.hh",
        fu / "base.hh",
        fu / "SConscript",
        ins / "base.hh",
        ins / "SConscript",
    ]
    for unit in units:
        outputs.extend((fu / (unit + ".hh"), fu / (unit + ".cc")))
    for name in instructions:
        outputs.extend((ins / (name + ".hh"), ins / (name + ".cc")))
    return outputs


def _generator_patch(text, model, period, profile):
    template_form = _detect_generator_template(text)
    if template_form == "legacy":
        text = _replace_once(
            text,
            "self.fu_list = os.listdir(self.yaml_dir)",
            "self.fu_list = sorted(os.listdir(self.yaml_dir))",
            "deterministic functional unit order",
        )
        return _replace_once(
            text,
            "generate_hw_models = HWModel(benchname=benchmark_args.bench, latency='5ns')",
            "generate_hw_models = HWModel(benchname=benchmark_args.bench, "
            "model={!r}, latency={!r}, profile={!r})".format(model, period, profile),
            "selected hardware profile",
        )
    else:  # canonical
        target = (
            "generate_hw_models = HWModel(benchname=benchmark_args.bench, "
            "model={!r}, latency={!r}, profile={!r})".format(model, period, profile)
        )
        current = (
            "generate_hw_models = HWModel(benchname=benchmark_args.bench, "
            "model=benchmark_args.model, latency=benchmark_args.latency, profile=benchmark_args.profile)"
        )
        if (model, period, profile) != ("40nm_model", "5ns", "default_profile"):
            text = _replace_once(text, current, target, "selected hardware profile")
        return text


def _require_scheduler_template(text):
    """Check generator integrity; do not grant engine scheduling capability."""
    required = (
        r'self.base_header_file.write("\t\tuint64_t _in_use = 0;\n\n")',
        r'self.base_header_file.write("\t\tuint64_t get_in_use() { return _in_use; }\n")',
        r'self.base_header_file.write("\t\tbool is_available() { return (_available == 0 || _in_use < _available); }\n")',
        "FU occupancy underflow",
    )
    if any(text.count(item) != 1 for item in required):
        raise ValueError("FU generator lacks an exact scheduler repair")


def _class_patch(text, *, capable=False):
    template_form = _detect_class_template(text)
    if template_form == "legacy":
        for name in FLOAT_FIELDS:
            text = _replace_once(
                text,
                r"\t" + name + " = Param.UInt32(",
                r"\t" + name + " = Param.Float(",
                "fractional " + name,
            )
        text = _replace_once(
            text,
            "self.inst_dict['instructions'][inst_name]['functional_unit_limit']",
            "self.inst_dict['instructions'][inst_name].get('functional_unit_limit', 0)",
            "optional instruction limit default",
        )
        if capable:
            _require_scheduler_template(text)
        else:
            # Preserve the explicitly supported historical repair route.
            text = _replace_once(
                text,
                r'self.base_header_file.write("\t\tuint64_t _in_use;\n\n")',
                r'self.base_header_file.write("\t\tuint64_t _in_use = 0;\n\n")',
                "initialized active unit count",
            )
            available_line = r'self.base_header_file.write("\t\tbool is_available() { return (_in_use >= _available); }\n")'
            getter_line = r'self.base_header_file.write("\t\tuint64_t get_in_use() { return _in_use; }\n")'
            text = _replace_once(
                text,
                available_line,
                getter_line + "\n            " + available_line,
                "active unit count getter",
            )
    else:
        # A missing/untrusted capability marker must not weaken validation
        # of canonical source. This check does not turn capability back on.
        _require_scheduler_template(text)
    return text


def _constructor_members(path):
    content = path.read_text(encoding="utf-8")
    return set(re.findall(r"_([a-z][a-z0-9_]*)\(params\.\1\)", content))


_FU_CONSTRUCTOR_FIELDS = (
    "alias",
    "stages",
    "cycles",
    "enum_value",
    "int_size",
    "int_sign",
    "int_apmode",
    "fp_size",
    "fp_sign",
    "fp_apmode",
    "ptr_size",
    "ptr_sign",
    "ptr_apmode",
    "limit",
    "power_units",
    "energy_units",
    "time_units",
    "area_units",
    "fu_latency",
) + FLOAT_FIELDS
_INST_CONSTRUCTOR_FIELDS = (
    "functional_unit",
    "functional_unit_limit",
    "opcode_num",
    "runtime_cycles",
)


def _cpp_without_comments(source):
    # These generated constructor/header templates contain no comment tokens
    # inside string literals. Fail closed if their shape changes.
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", source, flags=re.S)


def _parameter_arguments(arguments):
    if not re.fullmatch(
        r"\s*params\.[a-z][a-z0-9_]*(?:\s*,\s*params\.[a-z][a-z0-9_]*)*\s*",
        arguments,
    ):
        raise ValueError("Generated base arguments are not direct params fields")
    return tuple(re.findall(r"params\.([a-z][a-z0-9_]*)", arguments))


def _generated_constructor_contract(stage, units, instructions):
    """Witness real field routing through expanded or shared base constructors.

    This is structural generated-source evidence, not a simulator build or a
    proof that model coefficients are calibrated or used by the scheduler.
    """
    results = []
    for directory, base, names, fields in (
        ("functionalunits", "FunctionalUnitBase", units, _FU_CONSTRUCTOR_FIELDS),
        ("instructions", "InstConfigBase", instructions, _INST_CONSTRUCTOR_FIELDS),
    ):
        folder = stage / "src/hwacc/HWModeling/generated" / directory
        header = _cpp_without_comments((folder / "base.hh").read_text())
        # The value constructor remains the final storage consumer. Check every
        # field's own initializer, including float coefficients, not just the
        # presence of a template delegating call.
        start_type = (
            r"std::string\s+alias"
            if directory == "functionalunits"
            else r"uint32_t\s+functional_unit"
        )
        value = re.search(
            r"\b"
            + base
            + r"\s*\(\s*"
            + start_type
            + r"\s*,(?P<parameters>.*?)\)\s*:\s*(?P<initializers>.*?)\{\s*\}",
            header,
            re.S,
        )
        if value is None:
            raise ValueError("Missing generated value constructor: " + base)
        declared = (fields[0],) + tuple(
            re.findall(
                r"\b(?:std::string|uint32_t|double|bool)\s+([a-z][a-z0-9_]*)",
                value.group("parameters"),
            )
        )
        if declared != fields:
            raise ValueError("Generated value constructor field order differs: " + base)
        stored = re.findall(
            r"\b_([a-z][a-z0-9_]*)\s*\(\s*([a-z][a-z0-9_]*)\s*\)",
            value.group("initializers"),
        )
        for field in fields:
            if [argument for member, argument in stored if member == field] != [field]:
                raise ValueError(
                    "Generated base field is not stored exactly: " + base + "." + field
                )
        if directory == "functionalunits":
            for field in FLOAT_FIELDS:
                if not re.search(
                    r"\bdouble\s+" + field + r"\s*(?:,|$)", value.group("parameters")
                ):
                    raise ValueError(
                        "Generated coefficient parameter is not double: " + field
                    )
                if not re.search(r"\bdouble\s+_" + field + r"\s*;", header):
                    raise ValueError(
                        "Generated coefficient storage is not double: " + field
                    )
                if not re.search(
                    r"\bdouble\s+get_"
                    + field
                    + r"\s*\(\s*\)\s*\{\s*return\s+_"
                    + field
                    + r"\s*;\s*\}",
                    header,
                ):
                    raise ValueError(
                        "Generated coefficient getter is not double: " + field
                    )
        delegated = re.search(
            r"template\s*<\s*typename\s+Params\s*>\s*explicit\s+"
            + base
            + r"\s*\(\s*const\s+Params\s*&\s*params\s*\)\s*:\s*"
            + base
            + r"\s*\((?P<arguments>.*?)\)\s*\{\s*\}",
            header,
            re.S,
        )
        if (
            delegated is not None
            and _parameter_arguments(delegated.group("arguments")) != fields
        ):
            raise ValueError("Shared generated constructor fields differ: " + base)
        forms = set()
        for name in names:
            source = _cpp_without_comments((folder / (name + ".cc")).read_text())
            call = re.search(
                r"\b" + base + r"\s*\((?P<arguments>.*?)\)\s*\{\s*\}", source, re.S
            )
            if call is None:
                raise ValueError("Generated subclass has no base consumer: " + name)
            arguments = call.group("arguments").strip()
            if arguments == "params":
                if delegated is None:
                    raise ValueError(
                        "Generated subclass delegates to an absent shared constructor: "
                        + name
                    )
                forms.add("shared_params")
            elif _parameter_arguments(arguments) == fields:
                forms.add("expanded_params")
            else:
                raise ValueError("Generated subclass fields differ: " + name)
        results.append(
            {
                "base": base,
                "fields": list(fields),
                "subclasses_checked": len(names),
                "constructor_forms": sorted(forms),
                "base_header_sha256": _sha(folder / "base.hh"),
            }
        )
    return {
        "state": "passed",
        "scope": "generated C++ constructor field routing",
        "groups": results,
    }


_OVERRIDE_INTEGER_FIELDS = ("stages", "cycles", "limit", "fu_latency")
_OVERRIDE_UNIT_FIELDS = (
    "power_units",
    "energy_units",
    "time_units",
    "area_units",
)
_OVERRIDE_FIELDS = set(FLOAT_FIELDS + _OVERRIDE_INTEGER_FIELDS + _OVERRIDE_UNIT_FIELDS)


def _normalize_profile_overrides(overrides, *, allow_fu_limit=False):
    if overrides is None:
        return {}
    if not isinstance(overrides, dict):
        raise ValueError("Profile overrides must be a functional-unit mapping")
    normalized = {}
    for unit, fields in overrides.items():
        if (
            not isinstance(unit, str)
            or not NAME.fullmatch(unit)
            or not isinstance(fields, dict)
        ):
            raise ValueError("Invalid functional-unit override")
        values = {}
        for field, raw in fields.items():
            if field not in _OVERRIDE_FIELDS or isinstance(raw, bool):
                raise ValueError(
                    "Unsupported functional-unit profile field: " + str(field)
                )
            if field in _OVERRIDE_UNIT_FIELDS:
                if not isinstance(raw, str) or not raw or len(raw) > 32:
                    raise ValueError("Invalid profile unit: " + field)
                value = raw
            else:
                try:
                    number = Decimal(str(raw))
                except (InvalidOperation, ValueError) as error:
                    raise ValueError(
                        "Invalid numeric profile value: " + field
                    ) from error
                if not number.is_finite() or number < 0:
                    raise ValueError("Nonfinite or negative profile value: " + field)
                if field in _OVERRIDE_INTEGER_FIELDS:
                    if number != number.to_integral_value():
                        raise ValueError("Fractional integer profile field: " + field)
                    value = int(number)
                else:
                    value = float(number)
                if field == "limit" and value != 0 and not allow_fu_limit:
                    raise ValueError(
                        "Nonzero FU limit requires the source-verified FU scheduler"
                    )
            values[field] = value
        if values:
            normalized[unit] = values
    return normalized


def _stage_profile_overrides(
    engine, stage, benchmark, model, period, profile, overrides, units, inputs
):
    if set(overrides) - set(units):
        raise ValueError(
            "Override names unknown functional units: "
            + ", ".join(sorted(set(overrides) - set(units)))
        )
    base = (
        Path("benchmarks/sys_validation")
        / benchmark
        / "configs/hw_interface/functional_units"
        / model
        / period
        / profile
    )
    changed = []
    for unit, fields in sorted(overrides.items()):
        relative = base / unit / (unit + ".yml")
        path = stage / relative
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        model_data = data["functional_unit"]
        parameters = model_data["parameters"]
        power = model_data["power_model"]
        units_data = power["units"]
        for field, value in sorted(fields.items()):
            if field in ("stages", "cycles", "limit"):
                parameters[field] = value
            elif field == "fu_latency":
                power["latency"] = value
            elif field in _OVERRIDE_UNIT_FIELDS:
                units_data[field[:-6]] = value
            else:
                power[field] = value
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        source_sha = _sha(engine / relative)
        staged_sha = _sha(path)
        item = next(i for i in inputs if i["relative_path"] == relative.as_posix())
        if item["source_sha256"] != source_sha:
            raise ValueError("Source profile changed during staging")
        item["staged_sha256"] = staged_sha
        changed.append(
            {
                "relative_path": relative.as_posix(),
                "sha256": staged_sha,
                "source_engine_sha256": source_sha,
                "differs_from_engine": staged_sha != source_sha,
                "kind": "profile_data",
            }
        )
    return changed


def generate_hardware_code(
    engine_root,
    benchmark,
    evidence_dir,
    *,
    model="40nm_model",
    period="5ns",
    profile="default_profile",
    profile_overrides=None,
    timeout_seconds=120,
    python_executable="/usr/bin/python3.8",
):
    """Run historical hardware generation only in a new staged directory.

    A passed result means generated files exist and pass structural checks.
    It does not mean gem5 was rebuilt or the chosen hardware profile is
    characterized, effective, or simulation-valid.
    """
    for label, value in (
        ("benchmark", benchmark),
        ("model", model),
        ("period", period),
        ("profile", profile),
    ):
        if not isinstance(value, str) or not NAME.fullmatch(value):
            raise ValueError("Invalid " + label)
    engine = Path(engine_root).resolve(strict=True)
    from .fu_capability import inspect_fu_capability

    capable = inspect_fu_capability(engine)["supported"]
    profile_overrides = _normalize_profile_overrides(
        profile_overrides, allow_fu_limit=capable
    )
    if type(timeout_seconds) not in (int, float) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    evidence = Path(evidence_dir).resolve()
    if evidence == engine or engine in evidence.parents:
        raise ValueError("Evidence directory must be outside source engine")
    evidence.mkdir(parents=True, exist_ok=False)
    stage = evidence / "staged_engine"
    stage.mkdir()
    record = {
        "schema_version": 1,
        "kind": "salam_hardware_codegen",
        "state": "running",
        "valid": False,
        "simulation_ready": False,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "engine_root": str(engine),
        "staged_engine_root": str(stage),
        "selection": {
            "benchmark": benchmark,
            "model": model,
            "period": period,
            "profile": profile,
        },
        "inputs": [],
        "script_patches": [],
        "outputs": [],
        "profile_overrides": profile_overrides,
        "build_consumer_issues": [],
        "errors": [],
    }
    _save(evidence / "hardware-codegen.json", record)
    try:
        if not engine.is_dir():
            raise ValueError("Engine root must be a directory")
        for filename in SCRIPT_FILES:
            _copy_source(engine, stage, Path(filename), record["inputs"])
        units, instructions, inst_relative = _profile_inputs(
            engine, stage, benchmark, model, period, profile, record["inputs"]
        )
        record["units"] = units
        profile_outputs = _stage_profile_overrides(
            engine,
            stage,
            benchmark,
            model,
            period,
            profile,
            profile_overrides,
            units,
            record["inputs"],
        )
        record["instructions"] = instructions
        (stage / "src/hwacc/HWModeling/src").mkdir(parents=True)
        _patch(
            stage,
            "HWProfileGenerator.py",
            lambda source: _generator_patch(source, model, period, profile),
            record["script_patches"],
        )
        _patch(
            stage,
            "SALAMClassGenerator.py",
            lambda source: _class_patch(source, capable=capable),
            record["script_patches"],
        )
        record["generator_templates"] = {
            patch["relative_path"]: patch["template_form"]
            for patch in record["script_patches"]
            if "template_form" in patch
        }
        environment = {
            "PATH": "/usr/bin:/bin",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "C.UTF-8",
        }
        argv = [
            python_executable,
            "-B",
            "HWProfileGenerator.py",
            "-b",
            benchmark,
        ]
        record["command"] = {
            "argv": argv,
            "cwd": str(stage),
            "environment": environment,
            "timeout_seconds": timeout_seconds,
            "python_sha256": _sha(python_executable),
        }
        with (evidence / "generator.stdout").open("wb") as out, (
            evidence / "generator.stderr"
        ).open("wb") as err:
            try:
                process = subprocess.run(
                    argv,
                    cwd=str(stage),
                    env=environment,
                    stdout=out,
                    stderr=err,
                    timeout=timeout_seconds,
                    shell=False,
                )
            except subprocess.TimeoutExpired:
                record["state"] = "timed_out"
                raise RuntimeError("Hardware generator timed out")
        record["command"]["return_code"] = process.returncode
        if process.returncode != 0:
            raise RuntimeError("Hardware generator exited " + str(process.returncode))
        expected = _expected_outputs(units, instructions)
        for relative in expected:
            path = stage / relative
            if not path.is_file() or path.stat().st_size == 0 or path.is_symlink():
                raise ValueError("Missing generated file: " + relative.as_posix())
            if path.suffix == ".py" or path.name == "SConscript":
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            source = engine / relative
            original_sha = _sha(source) if source.is_file() else None
            digest = _sha(path)
            record["outputs"].append(
                {
                    "relative_path": relative.as_posix(),
                    "sha256": digest,
                    "source_engine_sha256": original_sha,
                    "differs_from_engine": digest != original_sha,
                    "kind": (
                        "compiled_source"
                        if path.suffix in (".cc", ".hh")
                        else "simobject_source"
                        if path.suffix == ".py"
                        else "build_declaration"
                    ),
                }
            )
        record["outputs"].extend(profile_outputs)
        changed_inst = _sha(stage / inst_relative) != next(
            item["source_sha256"]
            for item in record["inputs"]
            if item["relative_path"] == inst_relative.as_posix()
        )
        record["profile_instruction_list_mutated"] = changed_inst
        record["outputs"].append(
            {
                "relative_path": inst_relative.as_posix(),
                "sha256": _sha(stage / inst_relative),
                "source_engine_sha256": _sha(engine / inst_relative),
                "differs_from_engine": changed_inst,
                "kind": "profile_data",
            }
        )
        for item in record["inputs"]:
            original = engine / item["relative_path"]
            if _sha(original) != item["source_sha256"]:
                raise RuntimeError("Source engine changed during generation")
        fu_members = _constructor_members(
            _source(engine, Path("src/hwacc/HWModeling/src/functional_units.cc"))
        )
        inst_members = _constructor_members(
            _source(engine, Path("src/hwacc/HWModeling/src/instruction_config.cc"))
        )
        if fu_members != set(units):
            record["build_consumer_issues"].append(
                "functional_units.cc constructor members differ from generated units"
            )
        if inst_members != set(instructions):
            record["build_consumer_issues"].append(
                "instruction_config.cc constructor members differ from generated instructions"
            )
        record["constructor_witness"] = _generated_constructor_contract(
            stage, units, instructions
        )
        record["gem5_rebuild_required"] = any(
            item["differs_from_engine"] and item["kind"] != "profile_data"
            for item in record["outputs"]
        )
        record["state"] = "generated"
        record["valid"] = not record["build_consumer_issues"]
    except Exception as error:
        if record["state"] != "timed_out":
            record["state"] = "failed"
        record["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        record["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for filename in ("generator.stdout", "generator.stderr"):
            path = evidence / filename
            if path.is_file():
                record[filename + "_sha256"] = _sha(path)
        _save(evidence / "hardware-codegen.json", record)
    return record
