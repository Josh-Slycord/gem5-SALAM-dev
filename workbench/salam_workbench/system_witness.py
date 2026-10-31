"""Evidence for requested gem5 system options from effective simulator state.

This module uses only Python's standard library so a staged full-system
configuration may import capture_system before gem5 instantiates SimObjects.
The captured class names complement, but do not replace, config.ini evidence.
"""
import configparser
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

CPU_TYPES = {
    "DerivO3CPU": "O3CPU",
    "O3CPU": "O3CPU",
    "TimingSimpleCPU": "TimingSimpleCPU",
    "AtomicSimpleCPU": "AtomicSimpleCPU",
    "MinorCPU": "MinorCPU",
    "ArmO3CPU": "BaseO3CPU",
    "ArmTimingSimpleCPU": "BaseTimingSimpleCPU",
    "ArmAtomicSimpleCPU": "BaseAtomicSimpleCPU",
    "ArmMinorCPU": "BaseMinorCPU",
}
SIZE_UNITS = {
    "B": 1,
    "kB": 1024,
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
    "TB": 1024**4,
}
FREQ_UNITS = {
    "Hz": Decimal(1),
    "kHz": Decimal(1000),
    "MHz": Decimal(1000000),
    "GHz": Decimal(1000000000),
    "THz": Decimal(1000000000000),
}
TIME_UNITS = {
    "s": Decimal(1),
    "ms": Decimal("0.001"),
    "us": Decimal("0.000001"),
    "ns": Decimal("0.000000001"),
    "ps": Decimal("0.000000000001"),
}
CPU_SECTION = re.compile(r"^system\.cpu(?:[0-9]+)?$")


def _class_name(obj):
    return type(obj).__name__ if obj is not None else None


def _members(obj):
    if obj is None:
        return []
    if isinstance(obj, (list, tuple)):
        return list(obj)
    if type(obj).__name__ == "SimObjectVector":
        return list(obj)
    return [obj]


def capture_system(system, options=None):
    """Return JSON-safe live class and topology information before instantiate."""
    cpus = _members(getattr(system, "cpu", None))
    controllers = _members(getattr(system, "mem_ctrls", None))
    platform = getattr(system, "realview", None)
    return {
        "schema_version": 1,
        "kind": "salam_live_system_capture",
        "requested_options": dict(options or {}),
        "system_class": _class_name(system),
        "cpu_classes": [_class_name(cpu) for cpu in cpus],
        "memory_controller_classes": [_class_name(ctrl) for ctrl in controllers],
        "dram_classes": [
            _class_name(getattr(ctrl, "dram", None)) for ctrl in controllers
        ],
        "platform_class": _class_name(platform),
        "l1i_classes": [_class_name(getattr(cpu, "icache", None)) for cpu in cpus],
        "l1d_classes": [_class_name(getattr(cpu, "dcache", None)) for cpu in cpus],
        "l2_class": _class_name(getattr(system, "l2", None)),
        "workload_class": _class_name(getattr(system, "workload", None)),
    }


def _size(value):
    if type(value) is int:
        return value
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*", str(value))
    if not match or match.group(2) not in SIZE_UNITS:
        raise ValueError("Unsupported memory size: " + str(value))
    number = Decimal(match.group(1)) * SIZE_UNITS[match.group(2)]
    if number != int(number):
        raise ValueError("Memory size must resolve to whole bytes")
    return int(number)


def _ticks(value, simfreq):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)\s*", str(value))
    if not match:
        raise ValueError("Unsupported clock: " + str(value))
    number = Decimal(match.group(1))
    unit = match.group(2)
    if number <= 0:
        raise ValueError("Clock must be positive")
    if unit in FREQ_UNITS:
        return Decimal(simfreq) / (number * FREQ_UNITS[unit])
    if unit in TIME_UNITS:
        return Decimal(simfreq) * number * TIME_UNITS[unit]
    raise ValueError("Unsupported clock unit: " + unit)


def _simfreq(stats_path):
    if stats_path is None:
        return 1000000000000, "assumed_gem5_1e12"
    lines = Path(stats_path).read_text(encoding="utf-8", errors="replace").splitlines()
    matches = []
    for line in lines:
        match = re.match(r"^\s*simFreq\s+([0-9]+)(?:\s|$)", line)
        if match:
            matches.append(int(match.group(1)))
    if not matches or any(value != matches[0] for value in matches):
        raise ValueError("stats.txt lacks a consistent simFreq")
    return matches[-1], "stats.txt"


def _ini(path):
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    with Path(path).open("r", encoding="utf-8") as handle:
        parser.read_file(handle)
    return parser


def _sections(parser, expression):
    pattern = re.compile(expression)
    return [name for name in parser.sections() if pattern.fullmatch(name)]


def _value(parser, section, key):
    return (
        parser.get(section, key, fallback=None) if parser.has_section(section) else None
    )


def _ranges(value):
    if not value:
        return None
    pairs = re.findall(r"(\d+):(\d+)", value)
    if not pairs:
        return None
    spans = [(int(start), int(end)) for start, end in pairs]
    if any(end <= start for start, end in spans):
        return None
    return sum(end - start for start, end in spans)


def _bool(value):
    if type(value) is bool:
        return value
    if str(value).lower() in ("true", "1"):
        return True
    if str(value).lower() in ("false", "0"):
        return False
    raise ValueError("Expected Boolean value: " + str(value))


def _same_scalar(actual, expected, *, size=False):
    if actual is None:
        return None
    try:
        return int(actual) == (_size(expected) if size else int(expected))
    except (ValueError, InvalidOperation):
        return False


def witness_system(ini_path, spec_system, *, stats_path=None, runtime_system=None):
    """Compare requested knobs to config.ini and optional live capture.

    state is passed only when every requested option has a matching witness.
    Unknown/unobservable options remain explicitly unwitnessed. A mismatch is
    failed even when other options are unknown.
    """
    if not isinstance(spec_system, dict):
        raise ValueError("spec_system must be a mapping")
    if isinstance(runtime_system, (str, Path)):
        runtime_system = json.loads(Path(runtime_system).read_text(encoding="utf-8"))
    if runtime_system is not None and not isinstance(runtime_system, dict):
        raise ValueError("runtime_system must be a capture mapping or JSON path")
    result = {
        "schema_version": 1,
        "kind": "salam_system_witness",
        "state": "unavailable",
        "checks": {},
        "issues": [],
        "unmapped_options": [],
        "ini_path": str(ini_path),
        "stats_path": str(stats_path) if stats_path else None,
        "runtime_capture_available": runtime_system is not None,
    }
    try:
        parser = _ini(ini_path)
        simfreq, simfreq_source = _simfreq(stats_path)
        result["simfreq"] = simfreq
        result["simfreq_source"] = simfreq_source
    except (OSError, ValueError, configparser.Error) as error:
        result["issues"].append(type(error).__name__ + ": " + str(error))
        return result

    def add(name, requested, observed, source, equal):
        if equal is None:
            result["checks"][name] = {
                "status": "unwitnessed",
                "requested": requested,
                "observed": observed,
                "source": source,
            }
            result["unmapped_options"].append(name)
        else:
            status = "passed" if equal else "failed"
            result["checks"][name] = {
                "status": status,
                "requested": requested,
                "observed": observed,
                "source": source,
            }
            if not equal:
                result["issues"].append(
                    name + " does not match effective configuration"
                )

    cpu_sections = _sections(parser, r"system\.cpu(?:[0-9]+)?")
    cpu_types = [_value(parser, section, "type") for section in cpu_sections]
    l1i_sections = _sections(parser, r"system\.cpu(?:[0-9]+)?\.icache")
    l1d_sections = _sections(parser, r"system\.cpu(?:[0-9]+)?\.dcache")
    l2_sections = _sections(parser, r"system\.l2(?:[0-9]+)?")
    dram_sections = _sections(parser, r"system\.mem_ctrls(?:[0-9]+)?\.dram")

    for raw_name, requested in spec_system.items():
        name = raw_name.replace("_", "-")
        if name == "mem-size":
            observed = _ranges(_value(parser, "system", "mem_ranges"))
            add(
                raw_name,
                requested,
                observed,
                "config.ini:system.mem_ranges",
                observed == _size(requested) if observed is not None else None,
            )
        elif name == "cpu-type":
            expected = CPU_TYPES.get(str(requested), str(requested))
            add(
                raw_name,
                requested,
                cpu_types,
                "config.ini:system.cpu*.type",
                all(item == expected for item in cpu_types) if cpu_types else None,
            )
        elif name == "num-cpus":
            add(
                raw_name,
                requested,
                len(cpu_sections),
                "config.ini:system.cpu* sections",
                len(cpu_sections) == int(requested),
            )
        elif name == "cacheline-size":
            observed = _value(parser, "system", "cache_line_size")
            add(
                raw_name,
                requested,
                observed,
                "config.ini:system.cache_line_size",
                _same_scalar(observed, requested, size=True),
            )
        elif name == "caches":
            observed = {
                "icaches": len(l1i_sections),
                "dcaches": len(l1d_sections),
            }
            enabled = _bool(requested)
            equal = (
                bool(cpu_sections)
                and len(l1i_sections) == len(cpu_sections)
                and len(l1d_sections) == len(cpu_sections)
                if enabled
                else not l1i_sections and not l1d_sections
            )
            add(
                raw_name,
                requested,
                observed,
                "config.ini:system.cpu*.{i,d}cache",
                equal,
            )
        elif name == "l2cache":
            add(
                raw_name,
                requested,
                len(l2_sections),
                "config.ini:system.l2* sections",
                bool(l2_sections) == _bool(requested),
            )
        elif name in (
            "l1i-size",
            "l1d-size",
            "l2-size",
            "l1i-assoc",
            "l1d-assoc",
            "l2-assoc",
        ):
            kind = name[:3]
            sections = (
                l1i_sections
                if kind == "l1i"
                else l1d_sections
                if kind == "l1d"
                else l2_sections
            )
            field = "size" if name.endswith("size") else "assoc"
            observed = [_value(parser, section, field) for section in sections]
            equal = (
                all(
                    _same_scalar(value, requested, size=field == "size")
                    for value in observed
                )
                if observed
                else None
            )
            add(
                raw_name,
                requested,
                observed,
                "config.ini:" + ",".join(sections) + "." + field,
                equal,
            )
        elif name in ("sys-clock", "cpu-clock"):
            section = (
                "system.clk_domain" if name == "sys-clock" else "system.cpu_clk_domain"
            )
            observed = _value(parser, section, "clock")
            expected = _ticks(requested, simfreq)
            add(
                raw_name,
                requested,
                observed,
                "config.ini:" + section + ".clock;simFreq=" + simfreq_source,
                Decimal(observed) == expected if observed is not None else None,
            )
        elif name == "mem-channels":
            count = len(dram_sections)
            add(
                raw_name,
                requested,
                count,
                "config.ini:system.mem_ctrls*.dram",
                count == int(requested) if dram_sections else None,
            )
        elif name == "mem-ranks":
            values = [
                _value(parser, section, "ranks_per_channel")
                for section in dram_sections
            ]
            equal = (
                all(_same_scalar(value, requested) for value in values)
                if values
                else None
            )
            add(
                raw_name,
                requested,
                values,
                "config.ini:system.mem_ctrls*.dram.ranks_per_channel",
                equal,
            )
        elif name == "mem-type":
            classes = (runtime_system or {}).get("dram_classes")
            add(
                raw_name,
                requested,
                classes,
                "live:mem_ctrls*.dram class",
                all(value == str(requested) for value in classes) if classes else None,
            )
        elif name == "machine-type":
            actual = (runtime_system or {}).get("platform_class")
            add(
                raw_name,
                requested,
                actual,
                "live:realview class",
                actual == str(requested) if actual else None,
            )
        elif name == "dtb-file":
            actual = _value(parser, "system.workload", "dtb_filename")
            expected = "" if str(requested).lower() == "none" else str(requested)
            add(
                raw_name,
                requested,
                actual,
                "config.ini:system.workload.dtb_filename",
                actual == expected if actual is not None else None,
            )
        else:
            add(raw_name, requested, None, "no validated witness mapping", None)

    if result["issues"]:
        result["state"] = "failed"
    elif result["unmapped_options"]:
        result["state"] = "partial"
    else:
        result["state"] = "passed"
    return result
