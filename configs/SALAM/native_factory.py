# SPDX-License-Identifier: BSD-3-Clause
"""Direct GEMM-compatible construction using the retained SALAM typed ABI.

This route consumes the checked normalized model. It does not import or
execute generated benchmark Python, reread hardware YAML, or bind clocks
before Simulation.run applies its final scalar overrides.
"""

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _model_dict(model):
    """Internal adapter for the freshly normalized, trusted in-process model.

    This is not validation of serialized receipt JSON. makeHWAcc is the
    supported entry point and always normalizes source files for each launch.
    """
    if hasattr(model, "to_dict"):
        model = model.to_dict()
    if not isinstance(model, dict) or model.get("schema_version") != 1:
        raise ValueError("Native SALAM factory requires normalized schema 1")
    return model


def _configure_hardware(acc, spec, hardware, record, path):
    """Keep the same classes and active latency path as HWAccConfig.AccConfig."""
    requested = spec["hardware"] or {}
    acc.llvm_interface = hardware.LLVMInterface()
    acc.llvm_interface.in_file = spec["ir_path"]
    acc.hw_interface = hardware.HWInterface()
    acc.hw_interface.cycle_counts = hardware.CycleCounts()
    hardware._instantiate_functional_units(acc, requested)
    hardware._instantiate_instructions(acc, requested)
    hardware._apply_cycle_counts(acc, requested)
    acc.hw_interface.salam_power_model = hardware.SALAMPowerModel()
    acc.hw_interface.hw_statistics = hardware.HWStatistics()
    acc.hw_interface.simulator_config = hardware.SimulatorConfig()
    acc.hw_interface.opcodes = hardware.InstOpCodes()

    for suffix, obj in (
        ("llvm_interface", acc.llvm_interface),
        ("hw_interface", acc.hw_interface),
        ("hw_interface.cycle_counts", acc.hw_interface.cycle_counts),
        ("hw_interface.functional_units", acc.hw_interface.functional_units),
        ("hw_interface.inst_config", acc.hw_interface.inst_config),
        ("hw_interface.salam_power_model", acc.hw_interface.salam_power_model),
        ("hw_interface.hw_statistics", acc.hw_interface.hw_statistics),
        ("hw_interface.simulator_config", acc.hw_interface.simulator_config),
        ("hw_interface.opcodes", acc.hw_interface.opcodes),
    ):
        record["objects"].append(
            {"path": path + "." + suffix, "type": type(obj).__name__}
        )
    for name, cls in hardware._FU_REGISTRY.items():
        obj = getattr(acc.hw_interface.functional_units, name)
        if not isinstance(obj, cls):
            raise ValueError("Typed FU object was not created: " + name)
        configured = requested.get("functional_units", {}).get(name, {})
        for field, value in configured.items():
            if int(getattr(obj, field)) != value:
                raise ValueError("FU override did not reach Params: " + name)
        record["objects"].append(
            {
                "path": path + ".hw_interface.functional_units." + name,
                "type": type(obj).__name__,
                "requested_params": configured,
            }
        )
    for name, cls in hardware._INST_REGISTRY.items():
        obj = getattr(acc.hw_interface.inst_config, name)
        if not isinstance(obj, cls):
            raise ValueError("Typed instruction object was not created: " + name)
        configured = requested.get("instructions", {}).get(name, {})
        for field in ("functional_unit", "functional_unit_limit", "opcode_num"):
            if field in configured and int(getattr(obj, field)) != configured[field]:
                raise ValueError("Instruction override did not reach Params: " + name)
        if "runtime_cycles" in configured:
            target = hardware._CYCLE_COUNT_NAME_MAP.get(name, name)
            actual = getattr(acc.hw_interface.cycle_counts, target)
            if int(actual) != configured["runtime_cycles"]:
                raise ValueError(
                    "Logical runtime_cycles did not reach CycleCounts: " + name
                )
        record["objects"].append(
            {
                "path": path + ".hw_interface.inst_config." + name,
                "type": type(obj).__name__,
                "requested_params": configured,
                "latency_authority": "hw_interface.cycle_counts",
            }
        )


def _preflight(model, system, objects, hardware):
    """Reject unsupported models and name collisions before system mutation."""
    clusters = model.get("clusters")
    if not isinstance(clusters, list) or not clusters:
        raise ValueError("Normalized SALAM model has no clusters")
    cluster_names = set()
    for spec in clusters:
        name = spec["name"].lower()
        if name in cluster_names or hasattr(system, name):
            raise ValueError("Cluster name collides with system: " + name)
        cluster_names.add(name)
        names = set()
        reserved = set(dir(objects.AccCluster))
        reserved.update(("local_bus", "coherency_bus", "system", "cluster_cache"))
        for device in spec["dmas"] + spec["accelerators"]:
            key = device["name"]
            if key in names or key in reserved:
                raise ValueError("Cluster child name collision: " + key)
            names.add(key)
        accelerator_names = {acc["name"] for acc in spec["accelerators"]}
        for dma in spec["dmas"]:
            if dma["type"] != "NonCoherent":
                raise ValueError("Native factory supports NonCoherent DMA only")
            if dma["pio_masters"] != ["LocalBus"]:
                raise ValueError("Native DMA requires one LocalBus PIO master")
        for acc in spec["accelerators"]:
            for target in acc["pio_masters"] + acc["local_slaves"]:
                if target != "LocalBus" and target not in accelerator_names:
                    raise ValueError("Unknown accelerator connection: " + target)
            requested = acc["hardware"] or {}
            for fu_name in requested.get("functional_units", {}):
                if fu_name not in hardware._FU_REGISTRY:
                    raise ValueError("Unsupported typed FU: " + fu_name)
            for instruction, values in requested.get("instructions", {}).items():
                if instruction not in hardware._INST_REGISTRY:
                    raise ValueError(
                        "Unsupported typed instruction override: " + instruction
                    )
                if values.get("functional_unit_limit", 0) != 0:
                    raise ValueError("Nonzero instruction FU cap is unsupported")
            for memory in acc["memories"]:
                key = memory["name"]
                if key in names or key in reserved:
                    raise ValueError("Cluster child name collision: " + key)
                names.add(key)
                if memory["type"] != "SPM":
                    raise ValueError("Native factory supports SPM memory only")
                for connection in memory["connections"]:
                    if connection["accelerator"] not in accelerator_names:
                        raise ValueError("Unknown SPM connection target")
                    if connection["ports"] < 1:
                        raise ValueError("SPM connection requires positive ports")


def _build_clusters(options, system, model):
    """Internal construction from a freshly checked in-process model.

    Leave native clocks deferred. Serialized receipt/model JSON is evidence,
    not a supported configuration input to this private helper.

    The caller obtains the model from native_config.normalize_configuration.
    Returned evidence records construction and requested Params, not a
    successful simulation or measured physical-model accuracy.
    """
    import HWAccConfig as hardware
    from m5 import objects

    model = _model_dict(model)
    _preflight(model, system, objects, hardware)
    record = {
        "schema_version": 1,
        "kind": "salam_native_factory",
        "state": "constructed_not_instantiated",
        "model_sha256": hashlib.sha256(
            _canonical_json(model).encode("utf-8")
        ).hexdigest(),
        "hardware_configuration_source": "normalized_model",
        "legacy_yaml_reload": False,
        "generated_python_executed": False,
        "cpp_interface": "retained_typed_wrappers",
        "clock_binding": "deferred_to_final_Simulation.run_boundary",
        "clusters": [],
        "objects": [],
        "edges": [],
        "limitations": [
            "Only normalized NonCoherent DMA, accelerators and SPM are supported.",
            "Cluster cache construction remains identical to retained builder.",
            "Construction and Params checks do not prove simulation correctness.",
            "PPA coefficients are uncalibrated profile metadata.",
        ],
    }

    def edge(left, right, count=1):
        record["edges"].append({"from": left, "to": right, "count": count})

    for spec in model["clusters"]:
        name = spec["name"].lower()
        setattr(system, name, objects.AccCluster())
        cluster = getattr(system, name)
        path = "system." + name
        record["clusters"].append(
            {
                "path": path,
                "base_address": spec["base_address"],
                "top_address": spec["top_address"],
                "allocation_policy": "legacy_next_multiple_including_padding",
                "range_used_for_bridge": False,
            }
        )
        record["objects"].append({"path": path, "type": "AccCluster"})
        record["objects"].extend(
            (
                {"path": path + ".local_bus", "type": "NoncoherentXBar"},
                {"path": path + ".coherency_bus", "type": "CoherentXBar"},
            )
        )
        system.iobus.mem_side_ports = cluster.local_bus.cpu_side_ports
        edge("system.iobus.mem_side_ports", path + ".local_bus.cpu_side_ports")
        cluster._connect_caches(system, options, l2coherent=False)
        edge(path + ".coherency_bus.mem_side_ports", "system.membus.cpu_side_ports")
        gic = system.realview.gic

        # Preserve the retained order: DMA definitions, all accelerator
        # definitions, then accelerator wiring and their memory children.
        for dma in spec["dmas"]:
            obj = objects.NoncoherentDma(
                pio_addr=dma["pio_addr"],
                pio_size=dma["pio_size"],
                gic=gic,
                int_num=dma["interrupt_num"],
            )
            setattr(cluster, dma["name"], obj)
            obj.cluster_dma = cluster.local_bus.cpu_side_ports
            obj.max_req_size = dma["max_req_size"]
            obj.buffer_size = dma["buffer_size"]
            obj.dma = cluster.coherency_bus.cpu_side_ports
            cluster.local_bus.mem_side_ports = obj.pio
            dma_path = path + "." + dma["name"]
            record["objects"].append(
                {
                    "path": dma_path,
                    "type": "NoncoherentDma",
                    "params": {
                        "pio_addr": dma["pio_addr"],
                        "pio_size": dma["pio_size"],
                        "max_req_size": dma["max_req_size"],
                        "buffer_size": dma["buffer_size"],
                        "int_num": dma["interrupt_num"],
                    },
                }
            )
            edge(dma_path + ".cluster_dma", path + ".local_bus.cpu_side_ports")
            edge(dma_path + ".dma", path + ".coherency_bus.cpu_side_ports")
            edge(path + ".local_bus.mem_side_ports", dma_path + ".pio")
            edge(dma_path + ".gic", "system.realview.gic")
        for acc in spec["accelerators"]:
            obj = objects.CommInterface(
                devicename=acc["name"],
                gic=gic,
                pio_addr=acc["pio_addr"],
                pio_size=acc["pio_size"],
                int_num=acc["interrupt_num"],
            )
            setattr(cluster, acc["name"], obj)
            acc_path = path + "." + acc["name"]
            record["objects"].append(
                {
                    "path": acc_path,
                    "type": "CommInterface",
                    "params": {
                        "devicename": acc["name"],
                        "pio_addr": acc["pio_addr"],
                        "pio_size": acc["pio_size"],
                        "int_num": acc["interrupt_num"],
                    },
                }
            )
            edge(acc_path + ".gic", "system.realview.gic")
            _configure_hardware(obj, acc, hardware, record, acc_path)
        for acc in spec["accelerators"]:
            obj = getattr(cluster, acc["name"])
            acc_path = path + "." + acc["name"]
            for target in acc["local_slaves"]:
                if target == "LocalBus":
                    obj.local = cluster.local_bus.cpu_side_ports
                    target_path = path + ".local_bus.cpu_side_ports"
                else:
                    obj.local = getattr(cluster, target).pio
                    target_path = path + "." + target + ".pio"
                edge(acc_path + ".local", target_path)
            for master in acc["pio_masters"]:
                if master == "LocalBus":
                    obj.pio = cluster.local_bus.mem_side_ports
                    target_path = path + ".local_bus.mem_side_ports"
                else:
                    obj.pio = getattr(cluster, master).local
                    target_path = path + "." + master + ".local"
                edge(acc_path + ".pio", target_path)
            obj.enable_debug_msgs = acc["debug"]
            for memory in acc["memories"]:
                addr_range = objects.AddrRange(memory["address"], memory["range_end"])
                spm = objects.ScratchpadMemory(range=addr_range)
                setattr(cluster, memory["name"], spm)
                spm.conf_table_reported = False
                spm.ready_mode = memory["ready_mode"]
                spm.reset_on_scratchpad_read = memory["reset_on_read"]
                spm.read_on_invalid = memory["read_on_invalid"]
                spm.write_on_valid = memory["write_on_valid"]
                spm.port = cluster.local_bus.mem_side_ports
                memory_path = path + "." + memory["name"]
                record["objects"].append(
                    {
                        "path": memory_path,
                        "type": "ScratchpadMemory",
                        "params": {
                            "range_start": memory["address"],
                            "range_end_exclusive": memory["range_end"],
                            "ready_mode": memory["ready_mode"],
                            "reset_on_scratchpad_read": memory["reset_on_read"],
                            "read_on_invalid": memory["read_on_invalid"],
                            "write_on_valid": memory["write_on_valid"],
                        },
                    }
                )
                edge(memory_path + ".port", path + ".local_bus.mem_side_ports")
                for connection in memory["connections"]:
                    peer = getattr(cluster, connection["accelerator"])
                    for _ in range(connection["ports"]):
                        peer.spm = spm.spm_ports
                    edge(
                        path + "." + connection["accelerator"] + ".spm",
                        memory_path + ".spm_ports",
                        connection["ports"],
                    )
    return record


def _verify_expected_model(
    model, engine, expected_model_path, expected_model_sha256, expected_layout_sha256
):
    """Check a generated binding against fresh source normalization.

    Saved JSON never becomes a construction authority. The trusted model
    still comes from normalize_configuration immediately before this check.
    """
    values = (expected_model_path, expected_model_sha256, expected_layout_sha256)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError(
            "Native model binding requires path, semantic and layout hashes"
        )
    for digest in values[1:]:
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid expected native model hash")
    path = Path(expected_model_path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("Native model snapshot must be a regular contained path")
    path.relative_to(engine)
    if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > 16 * 1024**2:
        raise ValueError("Native model snapshot is not bounded regular data")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate native model snapshot key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Nonfinite native model snapshot value: " + value)

    raw = path.read_bytes()
    document = json.loads(
        raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant
    )
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    semantic = hashlib.sha256(canonical.encode()).hexdigest()
    if semantic != expected_model_sha256:
        raise ValueError("Native model snapshot semantic hash differs from wrapper")
    if model.sha256 != expected_model_sha256 or document != model.to_dict():
        raise ValueError("Fresh normalized configuration differs from generated model")
    if model.layout_sha256 != expected_layout_sha256:
        raise ValueError("Fresh normalized layout differs from generated headers")
    return {
        "path": str(path),
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "semantic_sha256": semantic,
        "layout_sha256": model.layout_sha256,
        "verified_against_fresh_sources": True,
    }


def makeHWAcc(
    options,
    system,
    *,
    expected_model_path=None,
    expected_model_sha256=None,
    expected_layout_sha256=None,
):
    """Entry point selected by --salam-builder=native in the retained runner."""
    import m5

    engine = Path(
        os.environ.get("M5_PATH") or Path(__file__).resolve().parents[2]
    ).resolve()
    workbench = str(engine / "workbench")
    if workbench not in sys.path:
        sys.path.insert(0, workbench)
    import HWAccConfig as hardware

    from salam_workbench import native_config

    imported_sources = {
        "hardware_adapter": Path(hardware.__file__).resolve(),
        "normalizer": Path(native_config.__file__).resolve(),
    }
    expected_sources = {
        "hardware_adapter": Path(__file__).with_name("HWAccConfig.py").resolve(),
        "normalizer": engine / "workbench/salam_workbench/native_config.py",
    }
    for name, source in imported_sources.items():
        if source != expected_sources[name]:
            raise ValueError("Native SALAM imported a different engine copy: " + name)

    config = getattr(options, "salam_config", None)
    if config is None:
        config = Path(options.accpath) / options.accbench / "config.yml"
    config = Path(config)
    if not config.is_absolute():
        config = engine / config
    if os.getenv("SALAM_EXPORT_CDFG", "").lower() in ("1", "true", "yes"):
        raise ValueError("SALAM_EXPORT_CDFG has no supported native SimObject consumer")
    model = native_config.normalize_configuration(
        config,
        engine,
        base_address=getattr(options, "salam_base_address", 0x10020000),
    )
    binding = _verify_expected_model(
        model,
        engine,
        expected_model_path,
        expected_model_sha256,
        expected_layout_sha256,
    )
    model = _model_dict(model)
    receipt = _build_clusters(options, system, model)
    receipt["generation_binding"] = binding
    outdir = Path(m5.options.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    model_path = outdir / "native_configuration.json"
    model_path.write_text(json.dumps(model, sort_keys=True, indent=2) + "\n")
    receipt["model_file"] = model_path.name
    receipt["model_file_sha256"] = _sha256(model_path)
    source_files = {
        "factory": Path(__file__).resolve(),
        **imported_sources,
    }
    receipt["source_files"] = {
        name: {"path": str(path), "sha256": _sha256(path)}
        for name, path in source_files.items()
    }
    (outdir / "native_factory.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    )
    return receipt
