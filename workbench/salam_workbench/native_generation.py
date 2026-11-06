# SPDX-License-Identifier: BSD-3-Clause
"""Normalized native preparation; no legacy topology generator is executed."""
import ast
import hashlib
import json
from pathlib import Path

from . import native_codegen, native_config, native_wrapper
from .build_inputs import address_macros

PROJECT = Path(__file__).resolve().parents[1]


def _record(path):
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n")


def _contained(root, path, *, exists=True):
    root = root.resolve(strict=True)
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve(strict=exists)
    resolved.relative_to(root)
    if resolved != path or path.is_symlink():
        raise ValueError("Native generation path must be ordinary contained data")
    return path


def _config(workspace, spec):
    return workspace / spec["benchmark"] / "config.yml"


def _base(spec):
    value = spec.get("base_address", "0x10020000")
    return int(value, 0) if isinstance(value, str) else value


def _module_path(workspace, spec):
    return workspace / "configs/SALAM/generated" / (spec["name"] + ".py")


def _fresh(workspace, spec, *, require_ir):
    return native_config.normalize_configuration(
        _config(workspace, spec),
        workspace,
        base_address=_base(spec),
        require_ir=require_ir,
    )


def _matching_frontend(workspace):
    pairs = (
        (
            Path(native_config.__file__),
            workspace / "workbench/salam_workbench/native_config.py",
        ),
        (
            PROJECT.parent / "configs/SALAM/native_factory.py",
            workspace / "configs/SALAM/native_factory.py",
        ),
    )
    records = []
    for host, staged in pairs:
        _contained(workspace, staged)
        if host.read_bytes() != staged.read_bytes():
            raise ValueError(
                "Staged native frontend differs from selected tooling: " + str(staged)
            )
        records.append(_record(staged))
    return records


def _check_generation_sources(workspace, generation):
    _matching_frontend(workspace)
    for source in generation["frontend_sources"] + [generation["template_source"]]:
        path = _contained(workspace, source["path"])
        if _record(path)["sha256"] != source["sha256"]:
            raise ValueError("Native generation source changed between phases")
    for source in generation["generation_sources"]:
        if _record(Path(source["path"]))["sha256"] != source["sha256"]:
            raise ValueError("Native rendering implementation changed between phases")


def prepare_headers(workspace, spec, directory):
    workspace = Path(workspace).resolve(strict=True)
    directory = Path(directory).resolve(strict=True)
    frontend_sources = _matching_frontend(workspace)
    if _module_path(workspace, spec).exists():
        raise ValueError("Native preparation refuses a generated topology module")
    model = _fresh(workspace, spec, require_ir=False)
    data = model.to_dict()
    benchmark = _contained(workspace, workspace / spec["benchmark"])
    existing = {}
    before = []
    for cluster in data["clusters"]:
        name = cluster.get("authored_name", cluster["name"])
        path = _contained(workspace, benchmark / (name + "_hw_defines.h"), exists=False)
        if path.exists():
            content = path.read_bytes()
            existing[name] = content.decode("utf-8")
            snapshot = directory / "native-header-inputs" / path.name
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(content)
            before.append(_record(snapshot))
    rendered = native_codegen.render_headers(model, existing_headers=existing)
    symbols = native_codegen.header_symbols(model)
    headers = []
    for name, text in rendered.items():
        path = _contained(workspace, benchmark / name, exists=False)
        path.write_bytes(text.encode("utf-8"))
        headers.append(dict(_record(path), symbols=symbols[name]))
    layout_path = directory / "native-layout-model.json"
    layout_path.write_text(model.to_json())
    result = {
        "kind": "salam_native_generation",
        "schema_version": 1,
        "state": "headers_prepared",
        "layout_sha256": model.layout_sha256,
        "layout_model": _record(layout_path),
        "headers": headers,
        "header_before_images": before,
        "frontend_sources": frontend_sources,
        "template_source": _record(
            _contained(workspace, workspace / "SALAM-Configurator/fs_template.py")
        ),
        "legacy_generator_executed": False,
        "topology_module_generated": False,
        "ir_bindings": [
            a["ir_path"] for c in data["clusters"] for a in c["accelerators"]
        ],
        "config_bindings": [
            str(_config(workspace, spec))
            for c in data["clusters"]
            for a in c["accelerators"]
        ],
        "generation_sources": [
            _record(Path(module.__file__))
            for module in (native_codegen, native_config, native_wrapper)
        ],
    }
    _save(directory / "native-generation.json", result)
    return result


def _check_headers(workspace, model, generation):
    expected = native_codegen.header_symbols(model)
    for record in generation["headers"]:
        path = _contained(workspace, record["path"])
        if _record(path)["sha256"] != record["sha256"]:
            raise ValueError("Normalized address header changed after generation")
        actual = address_macros([path])
        wanted = expected[path.name]
        if any(actual.get(name) != value for name, value in wanted.items()):
            raise ValueError("Normalized address header differs from model")
    if set(expected) != {Path(r["path"]).name for r in generation["headers"]}:
        raise ValueError("Normalized header set differs from model")


def finalize_wrapper(workspace, spec, directory, generation):
    workspace = Path(workspace).resolve(strict=True)
    directory = Path(directory).resolve(strict=True)
    _check_generation_sources(workspace, generation)
    model = _fresh(workspace, spec, require_ir=True)
    if model.layout_sha256 != generation["layout_sha256"]:
        raise ValueError("Normalized layout changed while compiling the workload")
    _check_headers(workspace, model, generation)
    generated = workspace / "configs/SALAM/generated"
    generated.mkdir(parents=True, exist_ok=True)
    snapshot = _contained(
        workspace, generated / ("native_" + spec["name"] + ".json"), exists=False
    )
    snapshot.write_text(model.to_json())
    template = _contained(workspace, workspace / "SALAM-Configurator/fs_template.py")
    wrapper = native_wrapper.render_wrapper(
        model, template.read_bytes().decode("utf-8"), model_path=snapshot
    )
    path = _contained(
        workspace, generated / ("fs_" + spec["name"] + ".py"), exists=False
    )
    path.write_text(wrapper.text)
    ast.parse(wrapper.text)
    record = dict(
        generation,
        state="wrapper_prepared",
        model_sha256=model.sha256,
        model=_record(snapshot),
        wrapper=_record(path),
        template=_record(template),
        wrapper_provenance=wrapper.provenance,
    )
    _save(directory / "native-generation.json", record)
    return record


def _with_runtime(text, request):
    needle = "test_sys = build_test_system(np)"
    if text.count(needle) != 1:
        raise ValueError("Native wrapper runtime hook is ambiguous")
    return text.replace(
        needle,
        needle + "\nfrom workbench_runtime import configure_system\n"
        "configure_system(test_sys, " + repr(str(request)) + ")",
    )


def bind_runtime(workspace, spec, directory, generation):
    """Capture the trusted runtime wiring output before a prepared run."""
    from .configurator import wire_runtime

    record = dict(
        generation, runtime_binding=wire_runtime(Path(workspace), spec, Path(directory))
    )
    _save(Path(directory) / "native-generation.json", record)
    return record


def _check_runtime_binding(workspace, directory, generation):
    binding = generation.get("runtime_binding")
    if not isinstance(binding, dict):
        raise ValueError("Native generation lacks trusted runtime wiring evidence")
    path = _contained(directory, binding["request"]["path"])
    if path != directory / "runtime-request.json":
        raise ValueError("Native runtime request path differs from wrapper")
    if _record(path)["sha256"] != binding["request"]["sha256"]:
        raise ValueError("Native runtime request changed after wiring")
    expected_names = {"workbench_runtime.py", "workbench_system_witness.py"}
    if {
        Path(item["staged"]["path"]).name for item in binding["modules"]
    } != expected_names:
        raise ValueError("Native runtime adapter set differs")
    for item in binding["modules"]:
        staged = _contained(workspace, item["staged"]["path"])
        selected = Path(item["selected"]["path"])
        if (
            _record(staged)["sha256"] != item["staged"]["sha256"]
            or _record(selected)["sha256"] != item["selected"]["sha256"]
            or item["staged"]["sha256"] != item["selected"]["sha256"]
        ):
            raise ValueError("Native runtime adapter differs from selected source")


def inspect_outputs(workspace, spec, directory, generation, *, final=False):
    workspace = Path(workspace).resolve(strict=True)
    directory = Path(directory).resolve(strict=True)
    _check_generation_sources(workspace, generation)
    if _module_path(workspace, spec).exists():
        raise ValueError("Native path unexpectedly contains generated topology Python")
    model = _fresh(workspace, spec, require_ir=final)
    if model.layout_sha256 != generation["layout_sha256"]:
        raise ValueError("Native generation layout no longer matches source inputs")
    _check_headers(workspace, model, generation)
    outputs = [_record(_contained(workspace, r["path"])) for r in generation["headers"]]
    result = dict(
        state="headers_prepared",
        builder="native",
        ir_bindings=generation["ir_bindings"],
        config_bindings=generation["config_bindings"],
        outputs=outputs,
        layout_sha256=model.layout_sha256,
        legacy_generator_executed=False,
        topology_module_generated=False,
    )
    if final:
        _check_runtime_binding(workspace, directory, generation)
        if model.sha256 != generation["model_sha256"]:
            raise ValueError(
                "Completed normalized inputs changed after wrapper generation"
            )
        path = _contained(workspace, generation["model"]["path"])
        if path.read_bytes() != model.to_json().encode():
            raise ValueError("Final normalized model snapshot changed")
        template = _contained(workspace, generation["template"]["path"])
        rendered = native_wrapper.render_wrapper(
            model, template.read_bytes().decode("utf-8"), model_path=path
        )
        wrapper_path = _contained(workspace, generation["wrapper"]["path"])
        expected = _with_runtime(rendered.text, directory / "runtime-request.json")
        actual = wrapper_path.read_text()
        if actual != expected:
            raise ValueError(
                "Prepared native wrapper differs from normalized renderer/runtime hook"
            )
        ast.parse(actual)
        result.update(
            state="generated",
            model_sha256=model.sha256,
            outputs=outputs + [_record(path), _record(wrapper_path)],
        )
        record = dict(generation, state="prepared", wrapper=_record(wrapper_path))
        _save(directory / "native-generation.json", record)
    return result


def witness_factory_binding(workspace, generation, simulator):
    """Reconcile captured construction with prepared identities, not pass flags."""
    workspace = Path(workspace).resolve(strict=True)
    simulator = Path(simulator).resolve(strict=True)
    receipt_path = simulator / "native_factory.json"
    receipt = json.loads(receipt_path.read_text())
    binding = receipt.get("generation_binding")
    if not isinstance(binding, dict):
        raise ValueError(
            "Native factory did not record the expected generation binding"
        )
    if (
        binding.get("semantic_sha256") != generation["model_sha256"]
        or binding.get("layout_sha256") != generation["layout_sha256"]
        or binding.get("path") != generation["model"]["path"]
        or binding.get("file_sha256") != generation["model"]["sha256"]
        or binding.get("verified_against_fresh_sources") is not True
        or receipt.get("model_sha256") != generation["model_sha256"]
    ):
        raise ValueError("Native factory binding differs from prepared generation")
    prepared = _contained(workspace, generation["model"]["path"])
    emitted = simulator / "native_configuration.json"
    if emitted.read_bytes() != prepared.read_bytes():
        raise ValueError("Constructed native model differs from generated snapshot")
    if _record(emitted)["sha256"] != receipt.get("model_file_sha256"):
        raise ValueError("Native factory model receipt differs from raw output")
    sources = receipt.get("source_files")
    expected_sources = {
        "factory": workspace / "configs/SALAM/native_factory.py",
        "hardware_adapter": workspace / "configs/SALAM/HWAccConfig.py",
        "normalizer": workspace / "workbench/salam_workbench/native_config.py",
    }
    if not isinstance(sources, dict) or set(sources) != set(expected_sources):
        raise ValueError(
            "Native factory source-role set differs from prepared frontend"
        )
    for role, expected in expected_sources.items():
        record = sources[role]
        if record.get("path") != str(expected):
            raise ValueError("Native factory source role points to a different file")
        source = _contained(workspace, record["path"])
        if _record(source)["sha256"] != record["sha256"]:
            raise ValueError("Native factory construction source changed")
    return {
        "state": "passed",
        "factory_receipt": _record(receipt_path),
        "model": _record(emitted),
        "semantic_sha256": generation["model_sha256"],
        "layout_sha256": generation["layout_sha256"],
        "scope": "Prepared and captured construction identities; numerical and event checks remain separate",
    }
