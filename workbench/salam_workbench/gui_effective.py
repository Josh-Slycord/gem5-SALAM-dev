"""Independent, fail-closed witness for a SALAM GUI apply-and-run request.

The GUI's displayed values, normalized pipeline specification, staged YAML,
generated bindings, gem5 config.ini, and compiled-profile receipts are
separate evidence layers. A passed state requires all of them to agree.
"""
import ast
import configparser
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from .config_contract import _Loader
from .fu_capability import inspect_fu_capability, requested_fu_capacity
from .hardware_codegen import _normalize_profile_overrides
from .profile_witness import witness_profiles
from .system_witness import witness_system


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _data(value):
    if isinstance(value, (str, Path)):
        return json.loads(Path(value).read_text(encoding="utf-8"))
    return value


def _equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def _check(result, field, requested, observed, source, matched):
    record = {
        "field": field,
        "requested": requested,
        "observed": observed,
        "source": source,
        "status": "passed" if matched else "failed",
    }
    result["checks"].append(record)
    if not matched:
        result["issues"].append({"field": field, "kind": "mismatch", "source": source})


def _fail(result, field, kind, detail):
    result["issues"].append({"field": field, "kind": kind, "detail": detail})


def _ini(path):
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    with Path(path).open(encoding="utf-8") as stream:
        parser.read_file(stream)
    return parser


def _observed(parser, section, field):
    return (
        parser.get(section, field, fallback=None)
        if parser.has_section(section)
        else None
    )


def _scalar(expected):
    if type(expected) is bool:
        return str(expected).lower()
    return str(expected)


def _number_equal(actual, requested):
    try:
        return Decimal(str(actual)) == Decimal(str(requested))
    except (InvalidOperation, TypeError, ValueError):
        return False


def _safe_source(root, relative):
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or ":" in relative
        or any(p in ("", ".", "..") for p in relative.split("/"))
    ):
        raise ValueError("Unsafe relative source path")
    base = Path(root).resolve(strict=True)
    target = (base / relative).resolve(strict=True)
    target.relative_to(base)
    if not target.is_file():
        raise ValueError("Source path is not a regular file")
    return target


def _documents(result, request, spec, workspace, gui_evidence, normalization):
    raw = request.get("configuration_documents")
    canonical = spec.get("configuration_documents")
    if not isinstance(raw, list) or not isinstance(canonical, list) or not canonical:
        _fail(
            result,
            "configuration_documents",
            "missing_documents",
            "GUI and spec need complete YAML documents",
        )
        return None
    if normalization is None:
        _check(
            result,
            "normalization",
            "receipt",
            None,
            "normalization.json",
            False,
        )
    else:
        receipt = _data(normalization)
        if not isinstance(receipt, dict):
            _fail(
                result,
                "normalization",
                "invalid_receipt",
                "Expected JSON mapping",
            )
        else:
            _check(
                result,
                "normalization.before",
                raw,
                receipt.get("configuration_documents_before"),
                "normalization.json",
                _equal(raw, receipt.get("configuration_documents_before")),
            )
            _check(
                result,
                "normalization.after",
                canonical,
                receipt.get("configuration_documents_after"),
                "normalization.json",
                _equal(canonical, receipt.get("configuration_documents_after")),
            )
            request_file = Path(gui_evidence) / "request.json"
            if request_file.is_file():
                _check(
                    result,
                    "normalization.raw_request_sha256",
                    _sha(request_file),
                    receipt.get("raw_request_sha256"),
                    "request.json/normalization.json",
                    _sha(request_file) == receipt.get("raw_request_sha256"),
                )
            else:
                _fail(
                    result,
                    "normalization.raw_request_sha256",
                    "missing_request",
                    str(request_file),
                )
            result["sources"]["normalization"] = (
                {"path": str(normalization), "sha256": _sha(normalization)}
                if isinstance(normalization, (str, Path))
                else {"inline": True}
            )
    config = Path(workspace) / spec.get("benchmark", "") / "config.yml"
    if not config.is_file():
        _fail(result, "staged_configuration", "missing_file", str(config))
        return None
    staged = list(yaml.load_all(config.read_text(encoding="utf-8"), Loader=_Loader))
    result["sources"]["staged_configuration"] = {
        "path": str(config),
        "sha256": _sha(config),
    }
    _check(
        result,
        "staged_configuration",
        canonical,
        staged,
        str(config),
        _equal(canonical, staged),
    )
    return staged


def _generated(result, docs, spec, workspace):
    name = spec.get("name")
    generated = Path(workspace) / "configs/SALAM/generated" / (str(name) + ".py")
    if not generated.is_file():
        _fail(result, "generated_topology", "missing_file", str(generated))
        return
    tree = ast.parse(generated.read_text(encoding="utf-8"))
    bindings = {"ir": [], "config": []}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in bindings
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            bindings[node.targets[0].id].append(node.value.value)
    ir, configs = [], []
    for doc in docs:
        for item in doc.get("acc_cluster", []):
            if "Accelerator" not in item:
                continue
            fields = {}
            for row in item["Accelerator"]:
                if "Var" not in row:
                    fields.update(row)
            ir.append(str(Path(workspace) / fields["IrPath"]))
            configs.append(
                str(Path(workspace) / fields["ConfigPath"])
                if "ConfigPath" in fields
                else str(Path(workspace) / spec["benchmark"] / "config.yml")
            )
    _check(
        result,
        "generated.ir_bindings",
        ir,
        bindings["ir"],
        str(generated),
        ir == bindings["ir"],
    )
    _check(
        result,
        "generated.profile_bindings",
        configs,
        bindings["config"],
        str(generated),
        configs == bindings["config"],
    )
    for kind, paths in (("ir", ir), ("profile", configs)):
        for index, path in enumerate(paths):
            target = Path(path)
            if not target.is_file():
                _fail(
                    result,
                    "generated.{}[{}]".format(kind, index),
                    "missing_bound_input",
                    str(target),
                )
            else:
                result["sources"]["generated.{}[{}]".format(kind, index)] = {
                    "path": str(target),
                    "sha256": _sha(target),
                }
    result["sources"]["generated_topology"] = {
        "path": str(generated),
        "sha256": _sha(generated),
    }


def _field(result, parser, field, section, key, expected, *, numeric=False):
    actual = _observed(parser, section, key)
    matched = (
        _number_equal(actual, expected) if numeric else actual == _scalar(expected)
    )
    _check(
        result,
        field,
        expected,
        actual,
        "config.ini:" + section + "." + key,
        matched,
    )


def _size(result, parser, field, section, requested):
    observed = _observed(parser, section, "range")
    match = re.fullmatch(r"(\d+):(\d+)", observed or "")
    actual = int(match.group(2)) - int(match.group(1)) if match else None
    _check(
        result,
        field,
        requested,
        actual,
        "config.ini:" + section + ".range",
        actual == requested,
    )


def _connections(raw):
    if raw is None:
        return []
    return [
        (a.strip().lower(), int(b))
        for a, b in (part.strip().split(":") for part in raw.split(","))
    ]


def _topology(result, docs, parser, base_address):
    graph = []
    first_address_witnessed = False
    for di, doc in enumerate(docs):
        entries = doc.get("acc_cluster", [])
        clusters = [row["Name"] for row in entries if "Name" in row]
        if len(clusters) != 1:
            _fail(
                result,
                "topology",
                "invalid_cluster",
                "Expected exactly one name per document",
            )
            continue
        cluster = clusters[0].lower()
        if not first_address_witnessed:
            first = next(
                (dma["Name"] for row in entries for dma in row.get("DMA", [])),
                None,
            )
            if first is None:
                first = next(
                    (
                        fields["Name"]
                        for row in entries
                        for fields in row.get("Accelerator", [])
                        if "Name" in fields
                    ),
                    None,
                )
            if first is not None:
                section = "system.{}.{}".format(cluster, first.lower())
                actual = _observed(parser, section, "pio_addr")
                _check(
                    result,
                    "topology.base_address",
                    base_address,
                    actual,
                    "config.ini:" + section + ".pio_addr",
                    _number_equal(actual, int(str(base_address), 0)),
                )
                first_address_witnessed = True
        for row in entries:
            if "DMA" in row:
                for dma in row["DMA"]:
                    name = dma["Name"].lower()
                    section = "system.{}.{}".format(cluster, name)
                    for yaml_key, ini_key in (
                        ("BufferSize", "buffer_size"),
                        ("MaxReqSize", "max_req_size"),
                        ("InterruptNum", "int_num"),
                    ):
                        if yaml_key in dma:
                            _field(
                                result,
                                parser,
                                "dma.{}.{}".format(name, yaml_key),
                                section,
                                ini_key,
                                dma[yaml_key],
                                numeric=True,
                            )
                    for port, peer in (
                        ("cluster_dma", ".local_bus.cpu_side_ports"),
                        ("dma", ".coherency_bus.cpu_side_ports"),
                        ("pio", ".local_bus.mem_side_ports"),
                    ):
                        actual = _observed(parser, section, port)
                        matched = actual is not None and actual.startswith(
                            "system." + cluster + peer
                        )
                        _check(
                            result,
                            "graph.{}.{}".format(name, port),
                            peer,
                            actual,
                            "config.ini:" + section + "." + port,
                            matched,
                        )
                    graph.append({"device": section, "kind": "dma"})
            elif "Accelerator" in row:
                fields, variables = {}, []
                for item in row["Accelerator"]:
                    if "Var" in item:
                        variables.extend(item["Var"])
                    else:
                        fields.update(item)
                owner = fields["Name"].lower()
                section = "system.{}.{}".format(cluster, owner)
                _field(
                    result,
                    parser,
                    "accelerator.{}.type".format(owner),
                    section,
                    "type",
                    "CommInterface",
                )
                if "Debug" in fields:
                    _field(
                        result,
                        parser,
                        "accelerator.{}.Debug".format(owner),
                        section,
                        "enable_debug_msgs",
                        fields["Debug"],
                    )
                ports = [("pio", ".local_bus.mem_side_ports")]
                if fields.get("LocalSlaves") == "LocalBus":
                    ports.append(("local", ".local_bus.cpu_side_ports"))
                for port, peer in ports:
                    actual = _observed(parser, section, port)
                    matched = actual is not None and actual.startswith(
                        "system." + cluster + peer
                    )
                    _check(
                        result,
                        "graph.{}.{}".format(owner, port),
                        peer,
                        actual,
                        "config.ini:" + section + "." + port,
                        matched,
                    )
                graph.append({"device": section, "kind": "accelerator"})
                for var in variables:
                    memory = var["Name"].lower()
                    memory_section = "system.{}.{}".format(cluster, memory)
                    _size(
                        result,
                        parser,
                        "memory.{}.Size".format(memory),
                        memory_section,
                        var["Size"],
                    )
                    if var["Type"] == "SPM":
                        _field(
                            result,
                            parser,
                            "memory.{}.type".format(memory),
                            memory_section,
                            "type",
                            "ScratchpadMemory",
                        )
                        for yaml_key, ini_key in (
                            ("ReadyMode", "ready_mode"),
                            ("ResetOnRead", "reset_on_scratchpad_read"),
                            ("ReadOnInvalid", "read_on_invalid"),
                            ("WriteOnValid", "write_on_valid"),
                        ):
                            if yaml_key in var:
                                _field(
                                    result,
                                    parser,
                                    "memory.{}.{}".format(memory, yaml_key),
                                    memory_section,
                                    ini_key,
                                    var[yaml_key],
                                )
                        expected = [(owner, var.get("Ports", 1))] + _connections(
                            var.get("Connections")
                        )
                        actual = (
                            _observed(parser, memory_section, "spm_ports") or ""
                        ).split()
                        peers = []
                        for target, count in expected:
                            pattern = re.compile(
                                r"^system\.{}\.{}\.spm\[\d+\]$".format(
                                    re.escape(cluster), re.escape(target)
                                )
                            )
                            observed = [p for p in actual if pattern.fullmatch(p)]
                            _check(
                                result,
                                "graph.{}.spm_ports.{}".format(memory, target),
                                count,
                                len(observed),
                                "config.ini:" + memory_section + ".spm_ports",
                                len(observed) == count,
                            )
                            peers.append(
                                {
                                    "target": target,
                                    "requested_ports": count,
                                    "observed_ports": len(observed),
                                }
                            )
                        _check(
                            result,
                            "graph.{}.spm_ports.total".format(memory),
                            sum(count for _, count in expected),
                            len(actual),
                            "config.ini:" + memory_section + ".spm_ports",
                            len(actual) == sum(count for _, count in expected),
                        )
                        port = _observed(parser, memory_section, "port")
                        _check(
                            result,
                            "graph.{}.local_bus".format(memory),
                            "system." + cluster + ".local_bus.mem_side_ports",
                            port,
                            "config.ini:" + memory_section + ".port",
                            port is not None
                            and port.startswith(
                                "system." + cluster + ".local_bus.mem_side_ports"
                            ),
                        )
                        graph.append(
                            {
                                "device": memory_section,
                                "kind": "spm",
                                "peers": peers,
                            }
                        )
                    elif var["Type"] == "RegisterBank":
                        _field(
                            result,
                            parser,
                            "memory.{}.type".format(memory),
                            memory_section,
                            "type",
                            "RegisterBank",
                        )
                        if any(
                            count != 1
                            for _, count in _connections(var.get("Connections"))
                        ):
                            _fail(
                                result,
                                "graph.{}.Connections".format(memory),
                                "unconsumed_register_ports",
                                "RegisterBank ignores connection port counts",
                            )
                        graph.append(
                            {"device": memory_section, "kind": "register_bank"}
                        )
                    else:
                        _fail(
                            result,
                            "memory.{}.Type".format(memory),
                            "unsupported_memory",
                            str(var["Type"]),
                        )
    result["graph"] = graph


def _hardware(
    result, docs, parser, workspace, overrides, *, fu_capacity_supported=False
):
    for doc in docs:
        clusters = [
            item["Name"] for item in doc.get("acc_cluster", []) if "Name" in item
        ]
        if len(clusters) != 1:
            continue
        cluster = clusters[0].lower()
        hardware = dict(doc.get("hw_config", {}))
        for item in doc.get("acc_cluster", []):
            if "Accelerator" not in item:
                continue
            fields = {}
            for row in item["Accelerator"]:
                if "Var" not in row:
                    fields.update(row)
            if "ConfigPath" not in fields:
                continue
            selected = _safe_source(workspace, fields["ConfigPath"])
            profile_docs = list(
                yaml.load_all(selected.read_text(encoding="utf-8"), Loader=_Loader)
            )
            if len(profile_docs) != 1 or not isinstance(profile_docs[0], dict):
                _fail(
                    result,
                    "hardware." + fields["Name"],
                    "invalid_external_profile",
                    "ConfigPath must contain exactly one YAML mapping",
                )
                continue
            stem = Path(fields["IrPath"]).stem
            settings = profile_docs[0].get("hw_config", {}).get(stem)
            if not isinstance(settings, dict) or not settings:
                _fail(
                    result,
                    "hardware." + stem,
                    "missing_external_profile",
                    "ConfigPath lacks active hardware settings",
                )
                continue
            hardware[stem] = settings
            result["sources"]["external_profile." + stem] = {
                "path": str(selected),
                "sha256": _sha(selected),
            }
        for name, settings in hardware.items():
            if not isinstance(settings, dict):
                continue
            base = "system.{}.{}.hw_interface".format(cluster, name.lower())
            for inst, fields in settings.get("instructions", {}).items():
                for key, value in fields.items():
                    if key == "functional_unit_limit" and value:
                        _fail(
                            result,
                            "instruction.{}.{}.functional_unit_limit".format(
                                name, inst
                            ),
                            "inactive_limit",
                            "Per-instruction limit has no scheduler consumer",
                        )
                    if key == "runtime_cycles":
                        section = base + ".cycle_counts"
                        if inst not in overrides.get(section, {}):
                            _field(
                                result,
                                parser,
                                "instruction.{}.{}.{}".format(name, inst, key),
                                section,
                                inst,
                                value,
                                numeric=True,
                            )
                    if key in (
                        "functional_unit",
                        "functional_unit_limit",
                        "opcode_num",
                    ):
                        section = base + ".inst_config." + inst
                        if key not in overrides.get(section, {}):
                            _field(
                                result,
                                parser,
                                "instruction.{}.{}.{}".format(name, inst, key),
                                section,
                                key,
                                value,
                                numeric=True,
                            )
            for unit, fields in settings.get("functional_units", {}).items():
                for key, value in fields.items():
                    if key in ("cycles", "limit"):
                        if key == "limit" and value and not fu_capacity_supported:
                            _fail(
                                result,
                                "functional_unit.{}.{}.limit".format(name, unit),
                                "inactive_limit",
                                "No verified compiled FU scheduler",
                            )
                        section = base + ".functional_units." + unit
                        if key not in overrides.get(section, {}):
                            _field(
                                result,
                                parser,
                                "functional_unit.{}.{}.{}".format(name, unit, key),
                                section,
                                key,
                                value,
                                numeric=True,
                            )


def _receipts(
    result,
    request,
    workspace,
    evidence,
    gui_evidence,
    build_receipt,
    generation_receipt,
    *,
    fu_capacity_supported=False,
):
    profile = request.get("hardware_profile", {})
    execution_path = Path(gui_evidence) / "gui-execution.json"
    if not execution_path.is_file():
        _fail(result, "gui_execution", "missing_receipt", str(execution_path))
        return
    execution = _data(execution_path)
    selected = execution.get("selected_engine")
    if not selected or not Path(selected).is_dir():
        _fail(
            result,
            "gui_execution.selected_engine",
            "missing_engine",
            str(selected),
        )
        return
    engine = Path(selected).resolve(strict=True)
    result["sources"]["gui_execution"] = {
        "path": str(execution_path),
        "sha256": _sha(execution_path),
    }
    if not isinstance(profile, dict):
        _fail(
            result,
            "hardware_profile",
            "invalid_profile",
            "Expected GUI profile mapping",
        )
        return
    if generation_receipt is None:
        _fail(
            result,
            "hardware_profile.generation",
            "missing_receipt",
            "A selected GUI profile requires generation",
        )
    else:
        generation = _data(generation_receipt)
        selection = generation.get("selection", {})
        for key in ("model", "period", "profile"):
            _check(
                result,
                "hardware_profile." + key,
                profile.get(key),
                selection.get(key),
                "hardware-codegen.json",
                profile.get(key) == selection.get(key),
            )
        _check(
            result,
            "hardware_profile.benchmark",
            Path(request.get("benchmark", "")).name,
            selection.get("benchmark"),
            "hardware-codegen.json",
            Path(request.get("benchmark", "")).name == selection.get("benchmark"),
        )
        normalized = _normalize_profile_overrides(
            profile.get("fu_overrides", {}),
            allow_fu_limit=fu_capacity_supported,
        )
        _check(
            result,
            "hardware_profile.fu_overrides",
            normalized,
            generation.get("profile_overrides", {}),
            "hardware-codegen.json",
            _equal(normalized, generation.get("profile_overrides", {})),
        )
        _check(
            result,
            "hardware_profile.generation_state",
            "generated/valid",
            [generation.get("state"), generation.get("valid")],
            "hardware-codegen.json",
            generation.get("state") == "generated" and generation.get("valid") is True,
        )
        # Generation may start from an archival source checkout and install
        # its verified outputs into a distinct selected build checkout.
        result["sources"]["generation_source_engine"] = generation.get("engine_root")
        kinds = {
            item.get("kind")
            for item in generation.get("outputs", [])
            if isinstance(item, dict)
        }
        _check(
            result,
            "hardware_profile.required_outputs",
            ["compiled_source", "simobject_source", "build_declaration"],
            sorted(kinds),
            "hardware-codegen.json",
            {"compiled_source", "simobject_source", "build_declaration"} <= kinds,
        )
        for item in generation.get("outputs", []):
            relative = item.get("relative_path")
            target = _safe_source(engine, relative)
            _check(
                result,
                "hardware_profile.installed_output." + relative,
                item.get("sha256"),
                _sha(target),
                "hardware-codegen.json/selected engine",
                _sha(target) == item.get("sha256"),
            )
            if item.get("kind") == "profile_data" and item.get("differs_from_engine"):
                staged = _safe_source(
                    generation.get("staged_engine_root", ""), relative
                )
                _check(
                    result,
                    "hardware_profile.staged_profile." + relative,
                    item.get("sha256"),
                    _sha(staged),
                    "hardware-codegen.json/staged profile input",
                    _sha(staged) == item.get("sha256"),
                )
        if not generation.get("outputs"):
            _fail(
                result,
                "hardware_profile.outputs",
                "empty_receipt",
                "No generated outputs",
            )
        if isinstance(generation_receipt, (str, Path)):
            result["sources"]["generation_receipt"] = {
                "path": str(generation_receipt),
                "sha256": _sha(generation_receipt),
            }
    if build_receipt is None:
        _fail(
            result,
            "simulator_build",
            "missing_receipt",
            "GUI run requires a rebuilt simulator receipt",
        )
    else:
        build = _data(build_receipt)
        _check(
            result,
            "simulator_build.state",
            "built",
            build.get("state"),
            "build.json",
            build.get("state") == "built",
        )
        binary = build.get("binary", {})
        _check(
            result,
            "simulator_build.binary_path",
            str(engine / "build/ARM/gem5.opt"),
            binary.get("path"),
            "build.json",
            str(engine / "build/ARM/gem5.opt") == binary.get("path"),
        )
        from .configurator import compiled_identity

        current_identity = compiled_identity(engine)
        _check(
            result,
            "simulator_build.compiled_source",
            build.get("compiled_source_sha256"),
            current_identity["sha256"],
            "build.json/current engine sources",
            build.get("compiled_source_sha256") == current_identity["sha256"],
        )
        if binary.get("path") and Path(binary["path"]).is_file():
            _check(
                result,
                "simulator_build.binary",
                binary.get("sha256"),
                _sha(binary["path"]),
                "build.json/binary",
                _sha(binary["path"]) == binary.get("sha256"),
            )
        else:
            _fail(
                result,
                "simulator_build.binary",
                "missing_binary",
                str(binary.get("path")),
            )
        pipeline = Path(evidence) / "configuration.json"
        if pipeline.is_file():
            record = _data(pipeline)
            _check(
                result,
                "pipeline.state",
                "passed",
                record.get("state"),
                str(pipeline),
                record.get("state") == "passed",
            )
            _check(
                result,
                "pipeline.simulation_requested",
                True,
                record.get("simulation_requested"),
                str(pipeline),
                record.get("simulation_requested") is True,
            )
            _check(
                result,
                "pipeline.run_state",
                "passed",
                record.get("run_state"),
                str(pipeline),
                record.get("run_state") == "passed",
            )
            numerical_state = (
                "independent_full_output_passed"
                if "benchmark_input" in request
                else "guest_checker_passed"
            )
            _check(
                result,
                "pipeline.numerical_correctness",
                numerical_state,
                record.get("numerical_correctness"),
                str(pipeline),
                record.get("numerical_correctness") == numerical_state,
            )
            if "benchmark_input" in request:
                _check(
                    result,
                    "pipeline.independent_oracle",
                    "passed",
                    record.get("independent_oracle", {}).get("state"),
                    str(pipeline),
                    record.get("independent_oracle", {}).get("state") == "passed",
                )
            completed = {
                Path(command.get("stdout", "")).name: command.get("state")
                == "completed"
                and command.get("return_code") == 0
                for command in record.get("commands", [])
                if isinstance(command, dict)
            }
            for label in ("generate", "build-ir", "build-guest"):
                _check(
                    result,
                    "pipeline.command." + label,
                    True,
                    completed.get(label + ".stdout"),
                    str(pipeline),
                    completed.get(label + ".stdout") is True,
                )
            _check(
                result,
                "pipeline.binary",
                binary.get("sha256"),
                record.get("engine", {}).get("binary", {}).get("sha256"),
                str(pipeline),
                binary.get("sha256")
                == record.get("engine", {}).get("binary", {}).get("sha256"),
            )
            _check(
                result,
                "pipeline.compiled_source",
                build.get("compiled_source_sha256"),
                record.get("engine", {}).get("compiled_source_sha256"),
                str(pipeline),
                build.get("compiled_source_sha256")
                == record.get("engine", {}).get("compiled_source_sha256"),
            )
            result["sources"]["pipeline"] = {
                "path": str(pipeline),
                "sha256": _sha(pipeline),
            }
        else:
            _fail(result, "pipeline", "missing_receipt", str(pipeline))
        if isinstance(build_receipt, (str, Path)):
            result["sources"]["build_receipt"] = {
                "path": str(build_receipt),
                "sha256": _sha(build_receipt),
            }


def witness_gui_effective(
    gui_request,
    spec,
    workspace,
    evidence_dir,
    config_ini,
    *,
    build_receipt=None,
    generation_receipt=None,
    normalization_receipt=None,
    gui_evidence_dir=None,
):
    """Compare one GUI request to the actual completed simulation, fail closed."""
    result = {
        "schema_version": 1,
        "kind": "salam_gui_effective_witness",
        "state": "failed",
        "checks": [],
        "issues": [],
        "sources": {},
        "graph": [],
        "limits": [
            "config.ini proves effective parameters and port wiring, not timing-model calibration"
        ],
    }
    try:
        request, spec = _data(gui_request), _data(spec)
        workspace, evidence, ini_path = (
            Path(workspace),
            Path(evidence_dir),
            Path(config_ini),
        )
        gui_evidence = (
            Path(gui_evidence_dir) if gui_evidence_dir is not None else evidence
        )
        if not isinstance(request, dict) or not isinstance(spec, dict):
            raise ValueError("GUI request and canonical spec must be mappings")
        execution_path = gui_evidence / "gui-execution.json"
        selected_engine = (
            _data(execution_path).get("selected_engine")
            if execution_path.is_file()
            else None
        )
        capability = inspect_fu_capability(selected_engine, build_receipt)
        result["fu_scheduler_capability"] = capability
        capable = capability["supported"]
        _check(
            result,
            "request.schema_version",
            2,
            request.get("schema_version"),
            "GUI request",
            request.get("schema_version") == 2,
        )
        _check(
            result,
            "request.action",
            "apply_and_run",
            request.get("action"),
            "GUI request",
            request.get("action") == "apply_and_run",
        )
        for key in (
            "benchmark",
            "system",
            "parameters",
            "base_address",
            "benchmark_input",
        ):
            _check(
                result,
                "request_to_spec." + key,
                request.get(key),
                spec.get(key),
                "GUI request/normalized specification",
                _equal(request.get(key), spec.get(key)),
            )
        source = request.get("provenance", {}).get("source_config", {})
        if source:
            original = _safe_source(request["engine_root"], source.get("relative_path"))
            _check(
                result,
                "source_config.sha256",
                source.get("sha256"),
                _sha(original),
                str(original),
                source.get("sha256") == _sha(original),
            )
            result["sources"]["source_config"] = {
                "path": str(original),
                "sha256": _sha(original),
            }
        else:
            _fail(
                result,
                "source_config",
                "missing_provenance",
                "GUI must record original YAML hash",
            )
        docs = _documents(
            result,
            request,
            spec,
            workspace,
            gui_evidence,
            normalization_receipt,
        )
        if docs is None:
            return result
        capacities = requested_fu_capacity(
            docs, request.get("hardware_profile", {}).get("fu_overrides", {})
        )
        if capacities and not capable:
            _fail(
                result,
                "fu_scheduler_capability",
                "missing_compiled_scheduler",
                "Requested FU capacity lacks a verified compiled scheduler: "
                + str(capability["reason"]),
            )
        editor = request.get("provenance", {}).get("editor_snapshot")
        if not isinstance(editor, dict):
            _fail(
                result,
                "editor_snapshot",
                "missing_snapshot",
                "GUI widget values are required",
            )
        else:
            if source:
                from .gui_editor import build_gui_request

                original_docs = list(
                    yaml.load_all(original.read_text(encoding="utf-8"), Loader=_Loader)
                )
                if len(original_docs) != 1:
                    _fail(
                        result,
                        "editor_snapshot.components",
                        "unsupported_source_documents",
                        "GUI editor requires exactly one source YAML document",
                    )
                else:
                    rerendered_request = build_gui_request(
                        original_docs[0],
                        editor,
                        benchmark=request["benchmark"],
                        engine_root=request["engine_root"],
                        distro=request["distro"],
                        source_config_relative=source["relative_path"],
                        source_config_sha256=source["sha256"],
                    )
                    rerendered = rerendered_request["configuration_documents"]
                    _check(
                        result,
                        "editor_snapshot.rendered_configuration",
                        request.get("configuration_documents"),
                        rerendered,
                        "source YAML + live widget snapshot",
                        _equal(request.get("configuration_documents"), rerendered),
                    )
                    for key in (
                        "base_address",
                        "system",
                        "parameters",
                        "benchmark_input",
                    ):
                        _check(
                            result,
                            "editor_snapshot." + key,
                            request.get(key),
                            rerendered_request.get(key),
                            "source YAML + live widget snapshot",
                            _equal(request.get(key), rerendered_request.get(key)),
                        )
                    raw_profile = editor["hardware_profile"]
                    canonical_profile = request.get("hardware_profile", {})
                    for key in ("model", "period", "profile"):
                        _check(
                            result,
                            "editor_snapshot.hardware_profile." + key,
                            canonical_profile.get(key),
                            raw_profile.get(key),
                            "live profile widget",
                            canonical_profile.get(key) == raw_profile.get(key),
                        )
                    raw_overrides = raw_profile.get("fu_overrides", {})
                    filtered_overrides = {
                        unit: {
                            field: value
                            for field, value in fields.items()
                            if value not in (None, "")
                        }
                        for unit, fields in raw_overrides.items()
                    }
                    normalized_overrides = _normalize_profile_overrides(
                        filtered_overrides, allow_fu_limit=capable
                    )
                    _check(
                        result,
                        "editor_snapshot.hardware_profile.fu_overrides",
                        canonical_profile.get("fu_overrides", {}),
                        normalized_overrides,
                        "live profile widget/typed numeric conversion",
                        _equal(
                            canonical_profile.get("fu_overrides", {}),
                            normalized_overrides,
                        ),
                    )
                    _check(
                        result,
                        "editor_snapshot.hardware_profile.reconstructed",
                        canonical_profile,
                        rerendered_request["hardware_profile"],
                        "source YAML + GUI editor conversion",
                        _equal(
                            canonical_profile,
                            rerendered_request["hardware_profile"],
                        ),
                    )
                    for unit, fields in filtered_overrides.items():
                        for field, raw_value in fields.items():
                            canonical_value = (
                                canonical_profile.get("fu_overrides", {})
                                .get(unit, {})
                                .get(field)
                            )
                            if field.endswith("_units"):
                                matched = raw_value == canonical_value
                            else:
                                try:
                                    matched = Decimal(str(raw_value)) == Decimal(
                                        str(canonical_value)
                                    )
                                except (
                                    InvalidOperation,
                                    TypeError,
                                    ValueError,
                                ):
                                    matched = False
                            _check(
                                result,
                                "editor_snapshot.hardware_profile.fu_overrides.{}.{}".format(
                                    unit, field
                                ),
                                raw_value,
                                canonical_value,
                                "raw widget/normalized profile value",
                                matched,
                            )
        _generated(result, docs, spec, workspace)
        parser = _ini(ini_path)
        result["sources"]["config_ini"] = {
            "path": str(ini_path),
            "sha256": _sha(ini_path),
        }
        _topology(result, docs, parser, request.get("base_address"))
        _hardware(
            result,
            docs,
            parser,
            workspace,
            request.get("parameters", {}),
            fu_capacity_supported=capable,
        )
        for section, fields in request.get("parameters", {}).items():
            for field, value in fields.items():
                _field(
                    result,
                    parser,
                    "parameters.{}.{}".format(section, field),
                    section,
                    field,
                    value,
                    numeric=type(value) in (int, float),
                )
        system = witness_system(
            ini_path,
            request.get("system", {}),
            stats_path=ini_path.parent / "stats.txt",
            runtime_system=Path(evidence) / "system-live.json",
        )
        result["system_witness"] = system
        _check(
            result,
            "system_witness",
            "passed",
            system["state"],
            "config.ini/stats.txt/system-live.json",
            system["state"] == "passed",
        )
        profile = witness_profiles(
            workspace,
            ini_path,
            parameter_overrides=request.get("parameters", {}),
        )
        result["profile_witness"] = profile
        _check(
            result,
            "profile_witness",
            "passed",
            profile["state"],
            "FunctionalUnits.py/config.ini",
            profile["state"] == "passed",
        )
        _receipts(
            result,
            request,
            workspace,
            evidence,
            gui_evidence,
            build_receipt,
            generation_receipt,
            fu_capacity_supported=capable,
        )
    except Exception as error:
        _fail(
            result,
            "witness",
            "exception",
            type(error).__name__ + ": " + str(error),
        )
    result["state"] = "passed" if not result["issues"] else "failed"
    return result
