"""Strict, deliberately narrow validator for the recovered GEMM M1 contract."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import yaml

CONTRACT = "gemm-m1-v1"
BASE_ADDRESS = 0x10020000
MAX_ADDRESS = 0x13FFFFFF
# Recovered config.yml at engine revision 42539ecca54ff0fed455a7afe0bda0603554e360.
# These are baseline assignments, not a claim that all assignments are optimal.
INSTRUCTION_BASELINE = {
    "add": (13, 1), "addrspacecast": (50, 0), "alloca": (31, 0),
    "and_inst": (28, 4), "ashr": (27, 3), "bitcast": (49, 0),
    "br": (2, 0), "call": (56, 0), "fadd": (14, 6), "fcmp": (54, 0),
    "fdiv": (21, 10), "fence": (35, 0), "fmul": (18, 9), "fpext": (46, 0),
    "fptosi": (42, 0), "fptoui": (41, 0), "fptrunc": (45, 0),
    "frem": (24, 0), "fsub": (16, 6), "gep": (34, 0), "icmp": (53, 0),
    "indirectbr": (4, 0), "inttoptr": (48, 0), "invoke": (5, 0),
    "landingpad": (66, 0), "load": (32, 0), "lshr": (26, 3), "mul": (17, 2),
    "or_inst": (29, 4), "phi": (55, 0), "ptrtoint": (47, 0),
    "resume": (6, 0), "ret": (1, 0), "sdiv": (20, 2), "select": (57, 0),
    "sext": (40, 0), "shl": (25, 3), "srem": (23, 0), "store": (33, 0),
    "sub": (15, 1), "switch_inst": (3, 0), "trunc": (38, 0), "udiv": (19, 2),
    "uitofp": (43, 0), "unreachable": (7, 0), "urem": (22, 0),
    "vaarg": (60, 0), "xor_inst": (30, 4), "zext": (39, 0),
}


class ConfigValidationError(ValueError):
    pass


class _UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ConfigValidationError("line %d: mapping keys must be strings" %
                                        (key_node.start_mark.line + 1))
        if key == "<<":
            raise ConfigValidationError("line %d: YAML merge keys are unsupported" %
                                        (key_node.start_mark.line + 1))
        if key in result:
            raise ConfigValidationError("line %d: duplicate YAML key %r" %
                                        (key_node.start_mark.line + 1, key))
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _fail(path, message):
    raise ConfigValidationError(path + ": " + message)


def _keys(value, required, path):
    if not isinstance(value, dict):
        _fail(path, "expected a mapping")
    missing = set(required) - set(value)
    unknown = set(value) - set(required)
    if missing:
        _fail(path, "missing required fields: " + ", ".join(sorted(missing)))
    if unknown:
        _fail(path, "unsupported fields for " + CONTRACT + ": " + ", ".join(sorted(unknown)))


def _sequence(value, count, path):
    if not isinstance(value, list) or len(value) != count:
        _fail(path, "expected exactly %d entries for %s" % (count, CONTRACT))


def _integer(value, path, minimum=0, maximum=0xFFFFFFFF):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(path, "expected integer in [%d, %d], not a boolean or float" % (minimum, maximum))


def _equal(value, expected, path):
    if type(value) is not type(expected) or value != expected:
        _fail(path, "expected %r for %s; received %r" % (expected, CONTRACT, value))


def _file(path, root, label):
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        _fail(label, "must resolve to an existing file inside engine_root (%s)" % error)
    if not resolved.is_file() or resolved.stat().st_size == 0:
        _fail(label, "must be a nonempty regular file")
    return resolved


def _fingerprint(path):
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def validate_gemm_config(path, engine_root, *, require_ir=True):
    """Validate only gemm-m1-v1; return evidence or raise ConfigValidationError.

    Allows nonnegative instruction latency/limit values but freezes opcode/FU
    assignments and the recovered GEMM topology. Validation does not prove that
    a parameter change takes effect in the simulator.
    """
    try:
        root = Path(engine_root).expanduser().resolve(strict=True)
    except OSError as error:
        _fail("engine_root", str(error))
    if not root.is_dir():
        _fail("engine_root", "must be a directory")
    source = Path(path).expanduser()
    if not source.is_absolute():
        source = root / source
    source = _file(source, root, "config")
    if source.stat().st_size > 1024 * 1024:
        _fail("config", "exceeds 1 MiB supported input limit")
    text = source.read_text(encoding="utf-8")
    try:
        if any(isinstance(token, yaml.tokens.AliasToken) for token in yaml.scan(text)):
            _fail("config", "YAML aliases are unsupported for this fixed contract")
        documents = list(yaml.load_all(text, Loader=_UniqueLoader))
    except yaml.YAMLError as error:
        _fail("config", "invalid YAML: " + str(error))
    if len(documents) != 1:
        _fail("config", "expected exactly one YAML document")
    data = documents[0]
    _keys(data, {"acc_cluster", "hw_config"}, "config")
    cluster = data["acc_cluster"]
    _sequence(cluster, 4, "acc_cluster")
    for index, key in enumerate(("Name", "DMA", "Accelerator", "Accelerator")):
        _keys(cluster[index], {key}, "acc_cluster[%d]" % index)
    _equal(cluster[0]["Name"], "gemm_clstr", "acc_cluster[0].Name")

    _sequence(cluster[1]["DMA"], 1, "acc_cluster[1].DMA")
    dma = cluster[1]["DMA"][0]
    _keys(dma, {"Name", "MaxReqSize", "BufferSize", "PIOMaster", "Type", "InterruptNum"},
          "acc_cluster[1].DMA[0]")
    for key, expected in (("Name", "dma"), ("PIOMaster", "LocalBus"),
                          ("Type", "NonCoherent"), ("InterruptNum", 95)):
        _equal(dma[key], expected, "DMA." + key)
    for key in ("MaxReqSize", "BufferSize"):
        _integer(dma[key], "DMA." + key, 1)
    if dma["MaxReqSize"] > dma["BufferSize"]:
        _fail("DMA.MaxReqSize", "must not exceed BufferSize")

    inputs = [_fingerprint(source)]
    pending_artifacts = []
    address = BASE_ADDRESS
    layout = [{"name": "dma", "address": address, "bytes": 21}]
    # Match parser.py's padding, including its extra 64 bytes for aligned sizes.
    address += 21 + (64 - 21 % 64)
    for index, name, pio, irname in ((2, "Top", 25, "top"), (3, "gemm", 1, "gemm")):
        entries = cluster[index]["Accelerator"]
        _sequence(entries, 1 if name == "Top" else 4, "Accelerator." + name)
        acc = entries[0]
        fields = {"Name", "IrPath", "PIOSize", "PIOMaster", "Debug"}
        if name == "Top":
            fields |= {"InterruptNum", "LocalSlaves"}
        _keys(acc, fields, "Accelerator." + name)
        for key, expected in (("Name", name), ("PIOSize", pio), ("PIOMaster", "LocalBus")):
            _equal(acc[key], expected, "Accelerator." + name + "." + key)
        if type(acc["Debug"]) is not bool:
            _fail("Accelerator." + name + ".Debug", "expected boolean")
        if name == "Top":
            _equal(acc["InterruptNum"], 68, "Accelerator.Top.InterruptNum")
            _equal(acc["LocalSlaves"], "LocalBus", "Accelerator.Top.LocalSlaves")
        expected_ir = "benchmarks/sys_validation/gemm/hw/" + irname + ".ll"
        _equal(acc["IrPath"], expected_ir, "Accelerator." + name + ".IrPath")
        ir_path = root / acc["IrPath"]
        if require_ir:
            ir = _file(ir_path, root, "Accelerator." + name + ".IrPath")
            inputs.append(_fingerprint(ir))
        else:
            try:
                ir_path.resolve().relative_to(root)
            except ValueError:
                _fail("Accelerator." + name + ".IrPath", "target escapes engine_root")
            c_source = _file(ir_path.with_suffix(".c"), root, "Accelerator." + name + ".CSource")
            inputs.append(_fingerprint(c_source))
            pending_artifacts.append({"path": str(ir_path), "state": "requires_fresh_build_and_postbuild_validation"})
        layout.append({"name": name, "address": address, "bytes": pio})
        address += pio + (64 - pio % 64)
        if name == "gemm":
            for offset, matrix in enumerate(("MATRIX1", "MATRIX2", "MATRIX3"), 1):
                item = entries[offset]
                _keys(item, {"Var"}, "Accelerator.gemm[%d]" % offset)
                _sequence(item["Var"], 1, matrix + ".Var")
                var = item["Var"][0]
                _keys(var, {"Name", "Type", "Size", "Ports"}, matrix)
                _equal(var["Name"], matrix, matrix + ".Name")
                _equal(var["Type"], "SPM", matrix + ".Type")
                _integer(var["Size"], matrix + ".Size", 8 * 8 * 4)
                _integer(var["Ports"], matrix + ".Ports", 1, 1024)
                if var["Size"] % 4:
                    _fail(matrix + ".Size", "must align to 4-byte integer elements")
                layout.append({"name": matrix, "address": address, "bytes": var["Size"]})
                address += var["Size"] + (64 - var["Size"] % 64)
    if address > MAX_ADDRESS:
        _fail("acc_cluster", "generated address range exceeds 0x13ffffff")

    hw = data["hw_config"]
    _keys(hw, {"name", "top", "gemm"}, "hw_config")
    _equal(hw["name"], "gemm_clstr", "hw_config.name")
    _equal(hw["top"], None, "hw_config.top")
    _keys(hw["gemm"], {"instructions"}, "hw_config.gemm")
    instructions = hw["gemm"]["instructions"]
    _keys(instructions, set(INSTRUCTION_BASELINE), "hw_config.gemm.instructions")
    for name, baseline in INSTRUCTION_BASELINE.items():
        prefix = "hw_config.gemm.instructions." + name
        config = instructions[name]
        _keys(config, {"functional_unit", "functional_unit_limit", "opcode_num", "runtime_cycles"}, prefix)
        _equal(config["opcode_num"], baseline[0], prefix + ".opcode_num")
        _equal(config["functional_unit"], baseline[1], prefix + ".functional_unit")
        for key in ("functional_unit_limit", "runtime_cycles"):
            _integer(config[key], prefix + "." + key, 0, 0x7FFFFFFF)

    defines = _file(root / "benchmarks/sys_validation/gemm/defines.h", root, "defines.h")
    define_text = defines.read_text(encoding="utf-8")
    for name, value in (("TYPE", "int"), ("ROW", "8"), ("COL", "8")):
        if not re.search(r"(?m)^\s*#define\s+" + name + r"\s+" + value + r"\s*$", define_text):
            _fail("defines.h", "expected explicit #define %s %s for %s" % (name, value, CONTRACT))
    if not re.search(r"(?m)^\s*#define\s+CHECK\s*$", define_text):
        _fail("defines.h", "CHECK must be explicitly enabled")
    inputs.append(_fingerprint(defines))
    return {
        "schema_version": 1, "validator": CONTRACT, "valid": True,
        "scope": "Fixed GEMM topology and source contract; not a general SALAM schema",
        "config": str(source), "inputs": inputs,
        "stage": "postbuild" if require_ir else "prebuild",
        "pending_artifacts": pending_artifacts,
        "instruction_count": len(instructions),
        "base_address": BASE_ADDRESS, "cluster_top_address": address, "layout": layout,
        "workload": {"rows": 8, "columns": 8, "type": "int", "check_defined": True},
        "limitations": [
            "Kernel semantics, effective simulator parameters and numerical correctness require execution evidence.",
            "Source macro text check supplements but does not replace compiler preprocessing.",
            "Generated addresses assume systembuilder.py default --base-address=0x10020000.",
            "No support claimed for other workloads, multiple clusters, Stream DMA or arbitrary topology.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config")
    parser.add_argument("--engine-root", required=True)
    parser.add_argument("--prebuild", action="store_true", help="Validate C inputs; IR must be built and revalidated before execution")
    args = parser.parse_args()
    try:
        result = validate_gemm_config(args.config, args.engine_root, require_ir=not args.prebuild)
    except (ConfigValidationError, OSError, UnicodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
