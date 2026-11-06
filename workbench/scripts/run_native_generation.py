#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Compare retained and normalized GEMM generation in separate workspaces.

Without --simulate, save only a plan. Simulation mode independently builds
both guest/header/IR paths, checks compiler-visible addresses and loaded
ELF images, then runs both builders with one canonical native-built ELF.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "workbench"))
sys.path.insert(0, str(ROOT / "workbench/scripts"))
import run_native_gemm as retained

from salam_workbench.native_codegen import header_symbols
from salam_workbench.native_config import normalize_configuration


def study_cases(selected=None, *, relocation_only=False):
    if selected is not None and relocation_only:
        raise ValueError("Choose explicit cases or relocation-only")
    rows = [] if relocation_only else retained.cases(selected)
    for row in rows:
        row["base_address"] = 0x10020000
    if selected is None:
        rows.append(
            dict(
                name="relocated-p3-cap1-lat16",
                period_ns=3,
                mul_limit=1,
                mul_cycles=16,
                base_address=0x10024000,
            )
        )
    return rows


def bounded_bytes(path, maximum=64 * 1024**2):
    """Read a bounded regular file without following a final symlink."""
    descriptor = os.open(Path(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ValueError("Not a bounded regular input: " + str(path))
        data = bytearray()
        while True:
            chunk = os.read(descriptor, min(1024**2, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > maximum:
                raise ValueError("Input exceeded bound while reading")
        after = os.fstat(descriptor)
        identity = lambda s: (
            s.st_dev,
            s.st_ino,
            s.st_size,
            s.st_mtime_ns,
            s.st_ctime_ns,
        )
        if identity(before) != identity(after) or len(data) != before.st_size:
            raise ValueError("Input changed while reading")
        return bytes(data)
    finally:
        os.close(descriptor)


def elf_load_image(path):
    """Describe the exact ARM ELF32 PT_LOAD bytes, BSS and entry contract."""
    data = bounded_bytes(path)
    if len(data) < 52:
        raise ValueError("Truncated ELF32 header")
    header = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    ident, elf_type, machine, version, entry, phoff, _, flags = header[:8]
    ehsize, phentsize, phnum = header[8:11]
    if ident[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("Expected little-endian ELF32 version 1")
    if elf_type != 2 or machine != 40 or version != 1:
        raise ValueError("Expected executable ARM ELF")
    if ehsize != 52 or phentsize != 32 or not 1 <= phnum <= 1024:
        raise ValueError("Invalid ELF program-header dimensions")
    if phoff < ehsize or phoff + phentsize * phnum > len(data):
        raise ValueError("ELF program-header table exceeds file")
    segments = []
    for index in range(phnum):
        fields = struct.unpack_from("<8I", data, phoff + index * phentsize)
        kind, offset, vaddr, paddr, filesz, memsz, permission, align = fields
        if kind != 1:
            continue
        if filesz > memsz or offset + filesz > len(data):
            raise ValueError("Invalid ELF PT_LOAD size or file span")
        if vaddr + memsz > 2**32 or paddr + memsz > 2**32:
            raise ValueError("ELF PT_LOAD address overflow")
        if align not in (0, 1) and (align & (align - 1) or (vaddr - offset) % align):
            raise ValueError("Invalid ELF PT_LOAD alignment")
        segments.append(
            {
                "program_header_index": index,
                "file_offset": offset,
                "virtual_address": vaddr,
                "physical_address": paddr,
                "file_bytes": filesz,
                "memory_bytes": memsz,
                "zero_fill_bytes": memsz - filesz,
                "flags": permission,
                "alignment": align,
                "payload_sha256": hashlib.sha256(
                    data[offset : offset + filesz]
                ).hexdigest(),
            }
        )
    if not segments:
        raise ValueError("ELF has no PT_LOAD segments")
    return {
        "path": str(Path(path).resolve()),
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "file_bytes": len(data),
        "entry": entry,
        "machine": machine,
        "flags": flags,
        "segments": segments,
    }


def compare_load_images(legacy, native):
    first, second = elf_load_image(legacy), elf_load_image(native)

    def semantics(image):
        return {
            "entry": image["entry"],
            "machine": image["machine"],
            "flags": image["flags"],
            "segments": [
                {
                    key: value
                    for key, value in segment.items()
                    if key not in ("program_header_index", "file_offset")
                }
                for segment in image["segments"]
            ],
        }

    equal = semantics(first) == semantics(second)
    return {
        "state": "passed" if equal else "failed",
        "scope": "Entry/machine/ABI flags and ordered PT_LOAD addresses, sizes, "
        "permissions, alignment, payload bytes and implicit zero-fill",
        "debug_sections_ignored": True,
        "legacy": first,
        "native": second,
        "load_image_equivalent": equal,
    }


def parse_header_macros(text):
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(
            r"\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s+"
            r"(0[xX][0-9a-fA-F]+|[0-9]+)\s*",
            line,
        )
        if match:
            name, value = match.groups()
            if name in result:
                raise ValueError("Duplicate integer header macro: " + name)
            result[name] = int(value, 0)
    return result


def compiler_header_witness(workspace, spec, expected, output):
    """Ask the real guest compiler which address macros its TU receives."""
    output.mkdir(parents=True, exist_ok=False)
    sw = workspace / spec["benchmark"] / "sw"
    argv = [
        "/usr/bin/arm-none-eabi-g++",
        "-E",
        "-dM",
        "-I",
        ".",
        "main-native.cpp",
    ]
    command = retained.command(
        argv, sw, output, "compiler-macros", retained._environment(workspace)
    )
    stdout = output / "compiler-macros.stdout"
    visible = parse_header_macros(stdout.read_text())
    differences = [
        {"macro": key, "expected": value, "observed": visible.get(key)}
        for key, value in expected.items()
        if visible.get(key) != value
    ]
    result = {
        "state": "passed" if not differences else "failed",
        "command": command,
        "compiler_sha256": retained.file_hash(Path(argv[0]).resolve()),
        "preprocessor_output_sha256": retained.file_hash(stdout),
        "translation_unit_sha256": retained.file_hash(sw / "main-native.cpp"),
        "expected": expected,
        "observed": {key: visible.get(key) for key in expected},
        "differences": differences,
    }
    retained.save(output / "witness.json", result)
    return result


def normalized_model(workspace, spec):
    return normalize_configuration(
        workspace / spec["benchmark"] / "config.yml",
        workspace,
        base_address=spec["base_address"],
    )


def generation_witnesses(legacy, native, legacy_spec, native_spec, directory):
    model = normalized_model(native, native_spec)
    expected = header_symbols(model)
    if len(expected) != 1:
        raise ValueError("Study requires one cluster header")
    filename, symbols = next(iter(expected.items()))
    first_header = legacy / legacy_spec["benchmark"] / filename
    second_header = native / native_spec["benchmark"] / filename
    maps = [
        parse_header_macros(bounded_bytes(path).decode("utf-8"))
        for path in (first_header, second_header)
    ]
    if maps[0] != maps[1] or maps[0] != symbols:
        raise ValueError("Complete retained/native/model header macros differ")
    compile_witnesses = [
        compiler_header_witness(root, spec, symbols, directory / (label + "-compiler"))
        for root, spec, label in (
            (legacy, legacy_spec, "legacy"),
            (native, native_spec, "native"),
        )
    ]
    if any(item["state"] != "passed" for item in compile_witnesses):
        raise ValueError("Compiler-visible header addresses differ")
    ir = []
    for actor in ("top", "gemm"):
        relative = Path(native_spec["benchmark"]) / "hw" / (actor + ".ll")
        left, right = legacy / relative, native / relative
        left_bytes, right_bytes = bounded_bytes(left), bounded_bytes(right)
        if left_bytes != right_bytes:
            raise ValueError("Separately generated LLVM IR differs: " + actor)
        ir.append(
            dict(
                actor=actor,
                legacy=str(left),
                native=str(right),
                sha256=hashlib.sha256(left_bytes).hexdigest(),
                bytes=len(left_bytes),
            )
        )
    preparation = directory / "native/preparation/native-generation.json"
    receipt = json.loads(preparation.read_text())
    if (
        receipt.get("legacy_generator_executed") is not False
        or receipt.get("topology_module_generated") is not False
    ):
        raise ValueError("Native generation receipt lacks generation boundaries")
    generated = "configs/SALAM/generated/" + native_spec["name"] + ".py"
    if (native / generated).exists() or not (legacy / generated).is_file():
        raise ValueError("Retained/native topology module presence disagrees")
    snapshot = (
        native / "configs/SALAM/generated" / ("native_" + native_spec["name"] + ".json")
    )
    snapshot_data = json.loads(snapshot.read_text())
    if snapshot_data != model.to_dict():
        raise ValueError("Final snapshot differs from fresh normalized model")
    left_elf = legacy / legacy_spec["benchmark"] / "sw/main-native.elf"
    right_elf = native / native_spec["benchmark"] / "sw/main-native.elf"
    image = compare_load_images(left_elf, right_elf)
    if image["state"] != "passed":
        raise ValueError("Independently built guest ELF load images differ")
    return {
        "state": "passed",
        "headers": {
            "legacy": str(first_header),
            "native": str(second_header),
            "legacy_sha256": retained.file_hash(first_header),
            "native_sha256": retained.file_hash(second_header),
            "symbols": symbols,
        },
        "compiler_witnesses": compile_witnesses,
        "ir": ir,
        "guest_load_image": image,
        "canonical_kernel": str(right_elf),
        "canonical_kernel_sha256": retained.file_hash(right_elf),
        "layout_sha256": model.layout_sha256,
        "model_sha256": model.sha256,
        "generation_receipt": str(preparation),
        "generation_receipt_sha256": retained.file_hash(preparation),
        "guest_build_receipts": [
            {
                "path": str(directory / label / "guest-build.json"),
                "sha256": retained.file_hash(directory / label / "guest-build.json"),
            }
            for label in ("legacy", "native")
        ],
    }


def positive_case(engine, receipt, output, case, checker):
    directory = output / "cases" / case["name"]
    directory.mkdir(parents=True, exist_ok=False)
    legacy, legacy_spec, legacy_fixtures = retained.prepare(
        engine, receipt, directory / "legacy", case, builder="generated"
    )
    native, native_spec, native_fixtures = retained.prepare(
        engine, receipt, directory / "native", case, builder="native"
    )
    for first, second in zip(legacy_fixtures, native_fixtures):
        if bounded_bytes(first) != bounded_bytes(second):
            raise ValueError("Paired numerical fixtures differ")
    generation = generation_witnesses(
        legacy, native, legacy_spec, native_spec, directory
    )
    retained.save(directory / "generation-comparison.json", generation)
    kernel = Path(generation["canonical_kernel"])
    first = retained.launch(
        engine,
        legacy,
        legacy_spec,
        directory / "legacy",
        "generated",
        kernel=kernel,
    )
    second = retained.launch(
        engine,
        native,
        native_spec,
        directory / "native",
        "native",
        kernel=kernel,
    )
    construction = retained.native_receipt(second["run_directory"])
    retained.save(directory / "native-construction.json", construction)
    comparison = checker.compare_runs(
        first["run_directory"],
        second["run_directory"],
        native_fixtures,
        expected_period_ns=case["period_ns"],
        expected_mul_limit=case["mul_limit"],
        expected_mul_cycles=case["mul_cycles"],
    )
    retained.save(directory / "comparison.json", comparison)
    if comparison["state"] != "passed":
        raise ValueError("Paired runtime comparison failed: " + str(directory))
    units = [
        item["units"][0]
        for item in comparison["direct"]["multiplier_capacity_witnesses"]
    ]
    if any(
        unit["grants"] != 512 or unit["releases"] != 512 or unit["outstanding"] != 0
        for unit in units
    ):
        raise ValueError("Expected 512 balanced multiply leases per launch")
    if case["mul_limit"] == 0:
        if any(unit["denials"] != 0 for unit in units):
            raise ValueError("Unlimited multiplier denied work")
    elif any(unit["peak"] != 1 or unit["denials"] < 1 for unit in units):
        raise ValueError("Finite multiplier did not restrict occupancy")
    return dict(
        case,
        state="passed",
        generation_receipt=str(directory / "generation-comparison.json"),
        numerical_receipt=str(directory / "comparison.json"),
        output_values_checked=256,
        multiplier_witnesses=units,
        observations=comparison["direct"]["observations"],
    )


def _diagnostic(record):
    directory = Path(record["run_directory"])
    return "\n".join(
        (directory / filename).read_text(errors="replace")
        for filename in ("stdout.txt", "stderr.txt", "simulator/system.terminal")
        if (directory / filename).is_file()
    )


def rejection_witness(record, expected):
    if record.get("state") != "failed" or expected not in _diagnostic(record):
        raise ValueError("Actual native process lacked expected rejection: " + expected)
    if type(record.get("process_id")) is not int:
        raise ValueError("Negative control lacks a recorded simulator process")
    return {
        "state": "passed",
        "run_directory": record["run_directory"],
        "process_id": record["process_id"],
        "expected_diagnostic": expected,
    }


def negative_cases(engine, receipt, output, checker):
    case = dict(period_ns=3, mul_limit=1, mul_cycles=16, base_address=0x10020000)
    controls = []

    directory = output / "controls/header-wrong-macro"
    workspace, spec, _ = retained.prepare(
        engine, receipt, directory, case, builder="native"
    )
    symbols = header_symbols(normalized_model(workspace, spec))
    filename, expected = next(iter(symbols.items()))
    header = workspace / spec["benchmark"] / filename
    shutil.copy2(header, directory / ("valid-" + filename))
    text = bounded_bytes(header).decode("utf-8")
    changed, count = re.subn(
        r"(?m)^#define TOP 0x[0-9a-fA-F]+$",
        "#define TOP " + hex(expected["TOP"] + 64),
        text,
    )
    if count != 1:
        raise ValueError("Header control requires one TOP definition")
    header.write_bytes(changed.encode("utf-8"))
    witness = compiler_header_witness(
        workspace, spec, expected, directory / "wrong-header-compiler"
    )
    if witness["state"] != "failed" or not any(
        item["macro"] == "TOP" and item["observed"] == expected["TOP"] + 64
        for item in witness["differences"]
    ):
        raise ValueError("Actual compiler did not expose wrong header macro")
    controls.append(
        dict(
            name="wrong_header_macro",
            state="passed",
            expected="Compiler succeeds; independent compiler-visible TOP witness rejects",
            witness=str(directory / "wrong-header-compiler/witness.json"),
            mutated_header_sha256=retained.file_hash(header),
        )
    )

    directory = output / "controls/false-guest-pass"
    workspace, spec, fixtures = retained.prepare(
        engine, receipt, directory, case, builder="native", corrupt=True
    )
    process = retained.launch(engine, workspace, spec, directory, "native")
    numerical = checker.verify_run(
        process["run_directory"],
        fixtures,
        expected_period_ns=3,
        expected_mul_limit=1,
        expected_mul_cycles=16,
    )
    retained.save(directory / "independent-rejection.json", numerical)
    if (
        process["state"] != "passed"
        or numerical.get("structural_state") != "passed"
        or numerical.get("numerical_state") != "failed"
    ):
        raise ValueError("False-green control did not isolate numerical rejection")
    controls.append(
        dict(
            name="false_guest_pass",
            state="passed",
            expected="Guest/runner green; independent numerical output check fails",
            witness=str(directory / "independent-rejection.json"),
        )
    )

    for name in ("model-tamper", "cli-base-override"):
        directory = output / ("controls/" + name)
        workspace, spec, _ = retained.prepare(
            engine, receipt, directory, case, builder="native"
        )
        if name == "model-tamper":
            snapshot = (
                workspace
                / "configs/SALAM/generated"
                / ("native_" + spec["name"] + ".json")
            )
            shutil.copy2(snapshot, directory / "valid-model.json")
            model = json.loads(snapshot.read_text())
            model["clusters"][0]["accelerators"][0]["pio_addr"] += 64
            retained.save(snapshot, model)
            mutation = dict(path=str(snapshot), sha256=retained.file_hash(snapshot))
            expected = "Native model snapshot semantic hash differs from wrapper"
        else:
            spec = dict(spec, base_address=0x10024000)
            mutation = dict(cli_base_address=spec["base_address"])
            expected = "CLI base address differs from the compiled guest layout"
        retained.save(directory / "controlled-mutation.json", mutation)
        process = retained.launch(
            engine, workspace, spec, directory, "native", required=False
        )
        result = rejection_witness(process, expected)
        result.update(name=name, mutation=mutation)
        retained.save(directory / "expected-rejection.json", result)
        controls.append(result)
    return controls


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--simulate", action="store_true")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--case",
        type=int,
        nargs=3,
        action="append",
        metavar=("PERIOD_NS", "FU_LIMIT", "MUL_CYCLES"),
    )
    selection.add_argument("--relocation-only", action="store_true")
    parser.add_argument("--skip-negatives", action="store_true")
    args = parser.parse_args(argv)
    args.engine = args.engine.resolve()
    args.build_receipt = args.build_receipt.resolve()
    selected = study_cases(args.case, relocation_only=args.relocation_only)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    plan = {
        "kind": "native_generation_differential_plan",
        "state": "planned",
        "cases": selected,
        "launches_per_simulator_process": 2,
        "fixture_seeds": [11, 29],
        "separate_generation_workspaces": True,
        "shared_native_built_kernel_after_load_image_proof": True,
        "negative_controls": not args.skip_negatives,
    }
    retained.save(out / "plan.json", plan)
    if not args.simulate:
        print(json.dumps(plan))
        return 0

    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    report = {
        "kind": "native_generation_differential_study",
        "state": "failed",
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "engine": str(args.engine.resolve()),
        "runner_sha256": retained.file_hash(Path(__file__)),
        "helper_sha256": retained.file_hash(Path(retained.__file__)),
        "cases": [],
        "negative_controls": [],
        "errors": [],
        "scope": "Fixed8x8int32GEMM; independent retained/native generation, "
        "complete macro/IR/ELF-load-image witnesses, shared canonical "
        "guest, numerical and timing/FU differential checks",
    }
    try:
        report["engine_before"] = retained.verify_engine(
            args.engine, args.build_receipt
        )
        checker = retained.checker_module()
        for case in selected:
            print("Running independent generation " + case["name"], flush=True)
            report["cases"].append(
                positive_case(args.engine, args.build_receipt, out, case, checker)
            )
            retained.save(out / "study.json", report)
        if not args.skip_negatives:
            report["negative_controls"] = negative_cases(
                args.engine, args.build_receipt, out, checker
            )
        report["engine_after"] = retained.verify_engine(args.engine, args.build_receipt)
        report["state"] = "passed"
    except Exception as error:
        report["errors"].append(type(error).__name__ + ": " + str(error))
    report["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    retained.save(out / "study.json", report)
    print(
        json.dumps(
            {
                "state": report["state"],
                "completed_cases": len(report["cases"]),
                "negative_controls": len(report["negative_controls"]),
                "errors": report["errors"],
                "receipt": str(out / "study.json"),
            }
        )
    )
    return 0 if report["state"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
