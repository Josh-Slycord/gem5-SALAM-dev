"""Validate event-backed SALAM observability; quarantine explicit legacy formats.

This module reads evidence only. Contract validation is not a claim of calibrated
hardware timing, power, cache behavior, or complete retired-instruction coverage.
"""
import argparse
import hashlib
import json
import re
from decimal import Decimal, localcontext
from pathlib import Path

from .runner import _safe_relative_path, _safe_run_file

KIND = "salam_observability"
VERSION = 1
PRODUCER = "workbench-m3"
MAX_UINT64 = (1 << 64) - 1
MAX_JSON_BYTES = 32 * 1024 * 1024
UNSUPPORTED = (
    "cache_hits",
    "fu_utilization",
    "power",
    "area",
    "dma",
    "total_retired_instructions",
)
LEGACY_FORMATS = ("legacy_nested_v3", "legacy_flat_v3")
MISSING = object()
DERIVED_PRECISION = 50


def _lookup(data, path):
    value = data
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return MISSING
        value = value[key]
    return value


def _pointer(path):
    return "/" + "/".join(
        key.replace("~", "~0").replace("/", "~1") for key in path.split(".")
    )


def _result(data):
    return {
        "kind": "salam_observability_validation",
        "status": "invalid",
        "contract_valid": False,
        "identity": {},
        "issues": [],
        "data": data,
        "metrics": {},
        "unsupported": {},
        "provenance": None,
    }


def _ratio_metric(metrics, name, numerator_path, denominator_path, unit, scope):
    numerator = metrics[numerator_path]
    denominator = metrics[denominator_path]
    entry = {
        "value": None,
        "unit": unit,
        "availability": "unknown",
        "scope": scope,
        "source_path": None,
        "source_paths": [numerator["source_path"], denominator["source_path"]],
        "derived": True,
        "derivation": {
            "operation": "arithmetic_mean",
            "numerator_path": numerator_path,
            "denominator_path": denominator_path,
            "numerator": numerator["value"],
            "denominator": denominator["value"],
            "decimal_significant_digits": DERIVED_PRECISION,
            "representation": "decimal_string",
            "exact_ratio": None,
        },
    }
    if numerator["availability"] == denominator["availability"] == "observed":
        if denominator["value"] == 0:
            entry["availability"] = "not_observed"
            entry["reason"] = "No observations in the declared denominator"
        else:
            with localcontext() as context:
                context.prec = DERIVED_PRECISION
                entry["value"] = format(
                    Decimal(numerator["value"]) / Decimal(denominator["value"]),
                    "f",
                )
            entry["availability"] = "observed"
            entry["derivation"]["exact_ratio"] = "{}/{}".format(
                numerator["value"], denominator["value"]
            )
    metrics[name] = entry


def validate_observability(data):
    """Validate exact v1 units, availability, lifecycle and aggregate invariants."""
    result = _result(data)
    issues, metrics = result["issues"], result["metrics"]
    if (
        not isinstance(data, dict)
        or data.get("kind") != KIND
        or type(data.get("schema_version")) is not int
        or data["schema_version"] != VERSION
    ):
        result["status"] = "unsupported_schema"
        issues.append(
            "Expected kind=salam_observability and integer schema_version=1; legacy requires an explicit adapter"
        )
        return result

    def number(path, unit, *, positive=False, nullable=False, scope=None):
        value = _lookup(data, path)
        entry = {
            "value": None,
            "unit": unit,
            "availability": "missing",
            "source_path": _pointer(path),
            "scope": scope,
        }
        metrics[path] = entry
        if value is MISSING:
            issues.append("Missing required field: " + path)
            return None
        if nullable and value is None:
            entry["availability"] = "not_observed"
            return None
        if (
            type(value) is not int
            or value < (1 if positive else 0)
            or value > MAX_UINT64
        ):
            entry.update(availability="invalid", raw_value=value)
            issues.append(
                "Expected an exact unsigned integer"
                + (" greater than zero" if positive else "")
                + ": "
                + path
            )
            return None
        entry.update(value=value, availability="observed")
        return value

    def flag(path, expected=None):
        value = _lookup(data, path)
        if type(value) is not bool or (expected is not None and value is not expected):
            issues.append("Invalid boolean or unsupported state: " + path)
            return None
        return value

    def text(path, expected=None):
        value = _lookup(data, path)
        if (
            not isinstance(value, str)
            or not value.strip()
            or (expected is not None and value != expected)
        ):
            issues.append("Missing or unsupported text value: " + path)
            return None
        return value

    def require(condition, message):
        if not condition:
            issues.append(message)

    text("producer", PRODUCER)
    accelerator = text("accelerator")
    invocation = number("invocation", "invocation", positive=True)
    if accelerator and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", accelerator):
        issues.append("Accelerator identity is not a safe SimObject name")
    result["identity"] = {"accelerator": accelerator, "invocation": invocation}
    flag("valid", True)
    flag("lifecycle.completed", True)
    life = {
        key: number("lifecycle." + key, "tick")
        for key in ("start_tick", "end_tick", "elapsed_ticks")
    }
    number("lifecycle.clock_period_ticks", "tick", positive=True)
    number("lifecycle.tick_frequency_hz", "tick/second", positive=True)
    calls = number("lifecycle.interface_tick_calls", "interface_tick_call")
    if all(value is not None for value in life.values()):
        require(
            life["end_tick"] >= life["start_tick"],
            "Lifecycle end precedes start",
        )
        require(
            life["elapsed_ticks"] == life["end_tick"] - life["start_tick"],
            "Lifecycle elapsed ticks do not equal end minus start",
        )

    text("memory.availability", "observed")
    memory_scope = text("memory.scope")
    memory = {}
    for direction in ("reads", "writes"):
        prefix = "memory." + direction
        values = {
            key: number(
                prefix + "." + key,
                "byte" if key.endswith("bytes") else "logical_request",
                scope=memory_scope,
            )
            for key in (
                "started",
                "completed",
                "started_bytes",
                "completed_bytes",
                "outstanding",
            )
        }
        latency = {
            key: number(
                prefix + ".latency_ticks." + key,
                "logical_request" if key == "count" else "tick",
                nullable=key in ("min", "max"),
                scope="Logical enqueue to final completion; queue waiting included",
            )
            for key in ("count", "sum", "min", "max")
        }
        memory[direction] = values
        if all(value is not None for value in values.values()):
            require(
                values["completed"] <= values["started"],
                prefix + ": completed exceeds started",
            )
            require(
                values["outstanding"] == values["started"] - values["completed"],
                prefix + ": outstanding count does not reconcile",
            )
            require(
                values["completed_bytes"] <= values["started_bytes"],
                prefix + ": completed bytes exceed started bytes",
            )
            if values["outstanding"] == 0:
                require(
                    values["started_bytes"] == values["completed_bytes"],
                    prefix + ": finished byte totals do not reconcile",
                )
            for count, size in (
                ("started", "started_bytes"),
                ("completed", "completed_bytes"),
            ):
                if values[count] == 0:
                    require(
                        values[size] == 0,
                        prefix + ": bytes recorded without corresponding requests",
                    )
        if values["completed"] is not None and latency["count"] is not None:
            require(
                latency["count"] == values["completed"],
                prefix + ": latency count does not match logical completions",
            )
        if latency["count"] == 0:
            require(
                latency["sum"] == 0
                and _lookup(data, prefix + ".latency_ticks.min") is None
                and _lookup(data, prefix + ".latency_ticks.max") is None,
                prefix + ": zero latency observations require sum=0 and null min/max",
            )
        elif latency["count"] is not None and latency["count"] > 0:
            if latency["min"] is None or latency["max"] is None:
                issues.append(prefix + ": observed latency extrema are missing")
            elif latency["sum"] is not None:
                require(
                    latency["min"] <= latency["max"],
                    prefix + ": latency minimum exceeds maximum",
                )
                require(
                    latency["count"] * latency["min"]
                    <= latency["sum"]
                    <= latency["count"] * latency["max"],
                    prefix + ": latency sum is outside count/extrema bounds",
                )
                if life["elapsed_ticks"] is not None:
                    require(
                        latency["max"] <= life["elapsed_ticks"],
                        prefix + ": request latency exceeds invocation window",
                    )

    text("execution.availability", "observed_selected_commits")
    execution_scope = text("execution.scope")
    commits = {
        key: number("execution." + key, "selected_commit", scope=execution_scope)
        for key in (
            "queued_compute_commits",
            "memory_read_commits",
            "memory_write_commits",
            "selected_commits_total",
        )
    }
    if all(value is not None for value in commits.values()):
        require(
            commits["selected_commits_total"]
            == sum(
                commits[key]
                for key in (
                    "queued_compute_commits",
                    "memory_read_commits",
                    "memory_write_commits",
                )
            ),
            "Selected commit totals do not reconcile",
        )
    for direction, name in (
        ("reads", "memory_read_commits"),
        ("writes", "memory_write_commits"),
    ):
        if commits[name] is not None and memory[direction]["completed"] is not None:
            require(
                commits[name] <= memory[direction]["completed"],
                "Selected memory commits exceed logical completions: " + direction,
            )

    text("queues.availability", "observed")
    text("queues.sample_unit", "accelerator_interface_tick_entry")
    text("queues.aggregation", "complete_streaming_sums_and_maxima")
    queue_scope = text("queues.scope")
    sample_count = number("queues.sample_count", "sample", scope=queue_scope)
    aggregated = number("queues.aggregated_sample_count", "sample", scope=queue_scope)
    dropped = number("queues.dropped_sample_count", "sample", scope=queue_scope)
    flag("queues.raw_samples_available", False)
    if sample_count is not None and aggregated is not None and calls is not None:
        require(
            sample_count == aggregated == calls,
            "Queue sample coverage does not equal interface tick calls",
        )
    require(dropped == 0, "Version 1 requires no dropped queue samples")
    for queue in (
        "reservation",
        "read",
        "write",
        "compute",
        "active_functions",
    ):
        unit = "active_function" if queue == "active_functions" else "queue_entry"
        total = number("queues." + queue + ".sum", unit + "*sample", scope=queue_scope)
        maximum = number("queues." + queue + ".max", unit, scope=queue_scope)
        if sample_count is not None and total is not None and maximum is not None:
            if sample_count == 0:
                require(
                    total == maximum == 0,
                    "Nonzero queue aggregates without samples: " + queue,
                )
                metrics["queues." + queue + ".max"].update(
                    value=None, raw_value=maximum, availability="not_observed"
                )
            else:
                require(
                    maximum <= total <= maximum * sample_count,
                    "Queue sum/max/sample count do not reconcile: " + queue,
                )

    invalid_events = number("diagnostics.invalid_events", "invalid_event")
    pending = number("diagnostics.pending_requests", "logical_request")
    require(invalid_events == 0, "Producer reported invalid collector events")
    require(pending == 0, "Completed invocation retains pending requests")
    outstanding = [
        memory[direction]["outstanding"] for direction in ("reads", "writes")
    ]
    if pending is not None and all(value is not None for value in outstanding):
        require(
            pending == sum(outstanding),
            "Pending request diagnostic does not match memory outstanding counts",
        )
    for name in UNSUPPORTED:
        text("unsupported." + name + ".availability", "unavailable")
        reason = text("unsupported." + name + ".reason")
        entry = _lookup(data, "unsupported." + name)
        if isinstance(entry, dict) and entry.get("value") is not None:
            issues.append(
                "Unavailable measurement must not carry a numeric value: " + name
            )
        result["unsupported"][name] = {
            "availability": "unavailable",
            "value": None,
            "unit": None,
            "reason": reason,
        }
    for direction in ("reads", "writes"):
        prefix = "memory." + direction + ".latency_ticks."
        _ratio_metric(
            metrics,
            prefix + "mean",
            prefix + "sum",
            prefix + "count",
            "tick",
            "Arithmetic mean across completed logical requests; enqueue-to-final-completion ticks, including queue waiting",
        )
    for queue in (
        "reservation",
        "read",
        "write",
        "compute",
        "active_functions",
    ):
        _ratio_metric(
            metrics,
            "queues." + queue + ".mean",
            "queues." + queue + ".sum",
            "queues.sample_count",
            "active_function" if queue == "active_functions" else "queue_entry",
            "Arithmetic mean of aggregate depths at interface tick entry, including initial/final samples; not per-function or time-weighted",
        )
    result["contract_valid"] = not issues
    result["status"] = "valid" if not issues else "invalid"
    return result


def adapt_legacy(data, format_name):
    """Preserve explicitly selected old fields, without validating their values."""
    result = _result(data)
    if (
        format_name not in LEGACY_FORMATS
        or not isinstance(data, dict)
        or data.get("kind") == KIND
    ):
        result["issues"].append(
            "Select legacy_nested_v3 or legacy_flat_v3 for a legacy JSON object"
        )
        return result
    payload = data.get("salam_stats", data)
    if not isinstance(payload, dict):
        result["issues"].append("Legacy salam_stats wrapper must contain an object")
        return result
    result.update(
        status="legacy_unvalidated",
        legacy_format=format_name,
        observed_version=payload.get("version"),
        identity={
            "accelerator": payload.get("accelerator_name"),
            "invocation": None,
        },
    )
    fields = {
        "host_setup_time": (
            "performance.setup_time_ns",
            "nanosecond",
            "Historical host profiling, not accelerator latency",
        ),
        "host_simulation_time": (
            "performance.sim_time_ns",
            "nanosecond",
            "Historical host profiling, not modeled latency",
        ),
        "interface_cycles": (
            "performance.total_cycles",
            "cycle",
            "Historical interface scope and unit unvalidated",
        ),
        "executed_nodes": (
            "performance.executed_nodes",
            "count",
            "Historical implementation does not establish retired instruction count",
        ),
        "power": (
            "power.total_power",
            "milliwatt as historically claimed",
            "No characterized model or validated activity coverage",
        ),
        "energy": (
            "power.total_energy_nj",
            "nanojoule as historically claimed",
            "Historical conversion and model defects unresolved",
        ),
        "area": (
            "area.total_area_um2",
            "square micrometre as historically claimed",
            "Model provenance unvalidated",
        ),
    }
    if format_name == "legacy_nested_v3":
        mapping = {
            "cache_hits": "cache.hits",
            "cache_misses": "cache.misses",
            "spm_reads": "spm.reads",
            "spm_writes": "spm.writes",
            "dma_reads": "dma.read_requests",
            "dma_writes": "dma.write_requests",
            "avg_read_latency": "latency.avg_read",
            "avg_write_latency": "latency.avg_write",
        }
    else:
        mapping = {
            name: name
            for name in (
                "cache_hits",
                "cache_misses",
                "spm_reads",
                "spm_writes",
                "dma_reads",
                "dma_writes",
                "avg_read_latency",
                "avg_write_latency",
            )
        }
    for name, path in mapping.items():
        fields[name] = (
            "memory_access." + path,
            "unknown" if "latency" in name else "count",
            "Event hookups and units were not independently validated in the recovered implementation",
        )
    prefix = "salam_stats." if "salam_stats" in data else ""
    for name, (path, unit, reason) in fields.items():
        raw = _lookup(payload, path)
        result["metrics"][name] = {
            "value": None,
            "unit": None,
            "availability": "missing" if raw is MISSING else "legacy_unvalidated",
            "raw_value": None if raw is MISSING else raw,
            "claimed_unit": unit,
            "source_path": _pointer(prefix + path),
            "scope": "historical source only",
            "reason": reason,
        }
    result["unsupported"] = {
        name: {
            "availability": "unknown",
            "value": None,
            "reason": "Legacy values do not establish current event-backed measurement coverage",
        }
        for name in UNSUPPORTED
    }
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Nonfinite JSON constant: " + value)


def load_observability(path, *, expected_sha256=None, legacy_format=None):
    """Read once, retain provenance, and validate current data or explicit legacy."""
    path = Path(path).expanduser().resolve()
    result = _result(None)
    provenance = {
        "path": str(path),
        "sha256": None,
        "expected_sha256": expected_sha256,
        "hash_verified": None,
    }
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ValueError("Observability JSON exceeds the 32 MiB limit")
        payload = path.read_bytes()
        provenance["sha256"] = hashlib.sha256(payload).hexdigest()
        if expected_sha256 is not None:
            provenance["hash_verified"] = (
                isinstance(expected_sha256, str)
                and re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256) is not None
                and provenance["sha256"] == expected_sha256.lower()
            )
        data = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        result = (
            adapt_legacy(data, legacy_format)
            if legacy_format is not None
            else validate_observability(data)
        )
        if expected_sha256 is not None and provenance["hash_verified"] is not True:
            result["issues"].append(
                "Observability file does not match its recorded SHA-256"
            )
            result.update(status="invalid", contract_valid=False)
    except (OSError, ValueError, UnicodeError) as error:
        result["issues"].append(type(error).__name__ + ": " + str(error))
    result["provenance"] = provenance
    return result


def assess_run_observability(run_dir, record, experiment):
    """Verify only declared, hash-recorded invocation artifacts and optional oracles.

    An absent observability contract is explicitly unavailable, not a failure of
    a historical numerical run. This helper does not mutate run.json or execute
    any process. The caller combines its result with numerical correctness.
    """
    result = {
        "status": "unavailable",
        "valid": None,
        "issues": [],
        "records": [],
        "expected_invocations": {},
        "observed_invocations": {},
    }
    if "observability" not in experiment:
        return result
    result.update(status="invalid", valid=False)
    contract = experiment["observability"]
    issues = result["issues"]
    if (
        not isinstance(contract, dict)
        or contract.get("kind") != KIND
        or type(contract.get("schema_version")) is not int
        or contract["schema_version"] != VERSION
    ):
        issues.append(
            "Observability contract requires kind=salam_observability and schema_version=1"
        )
        return result
    expected = contract.get("expected_invocations")
    if (
        not isinstance(expected, dict)
        or not expected
        or any(
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", name)
            or not isinstance(numbers, list)
            or not numbers
            or any(
                type(number) is not int or number < 1 or number > MAX_UINT64
                for number in numbers
            )
            or len(set(numbers)) != len(numbers)
            for name, numbers in expected.items()
        )
    ):
        issues.append(
            "expected_invocations must map safe accelerator names to distinct positive invocation numbers"
        )
        return result
    result["expected_invocations"] = expected
    directory = Path(run_dir).resolve()
    entries = record.get("artifacts", [])
    if not isinstance(entries, list):
        issues.append("Run artifact manifest must be a list")
        return result
    seen_paths, observed = set(), {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            issues.append("Malformed recorded artifact entry")
            continue
        relative = entry["path"].replace("\\", "/")
        if not relative.startswith("simulator/observability/"):
            continue
        try:
            relative = _safe_relative_path(relative)
            if relative in seen_paths:
                raise ValueError("Duplicate observability artifact path")
            seen_paths.add(relative)
            if not relative.endswith(".json") or not _safe_run_file(
                directory, relative
            ):
                raise ValueError(
                    "Observability artifact must be a local regular JSON file"
                )
            digest = entry.get("sha256")
            if (
                not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None
            ):
                raise ValueError(
                    "Observability artifact lacks a valid recorded SHA-256"
                )
            parsed = load_observability(directory / relative, expected_sha256=digest)
            parsed["artifact_path"] = relative
            result["records"].append(parsed)
            if not parsed["contract_valid"]:
                issues.extend(relative + ": " + issue for issue in parsed["issues"])
            identity = parsed["identity"]
            name, invocation = identity.get("accelerator"), identity.get("invocation")
            if not name or invocation is None:
                continue
            canonical = "simulator/observability/{}.invocation-{}.json".format(
                name, invocation
            )
            if relative != canonical:
                issues.append(
                    "Observability identity does not match its artifact filename: "
                    + relative
                )
            key = (name, invocation)
            if key in observed:
                issues.append("Duplicate accelerator invocation: " + repr(key))
            observed[key] = parsed
        except (OSError, ValueError, TypeError) as error:
            issues.append(relative + ": " + str(error))
    expected_pairs = {
        (name, number) for name, numbers in expected.items() for number in numbers
    }
    for key in sorted(expected_pairs - set(observed)):
        issues.append("Missing expected accelerator invocation: " + repr(key))
    for key in sorted(set(observed) - expected_pairs):
        issues.append("Unexpected accelerator invocation: " + repr(key))
    for name, number in sorted(observed):
        result["observed_invocations"].setdefault(name, []).append(number)
    oracles = contract.get("oracles", {})
    if not isinstance(oracles, dict):
        issues.append("Observability oracles must be an object")
    else:
        for name, checks in oracles.items():
            if name not in expected or not isinstance(checks, dict):
                issues.append(
                    "Oracle names an undeclared accelerator or malformed checks: "
                    + str(name)
                )
                continue
            for path, wanted in checks.items():
                if (
                    not isinstance(path, str)
                    or not re.fullmatch(
                        r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*",
                        path,
                    )
                    or type(wanted) is not int
                    or wanted < 0
                    or wanted > MAX_UINT64
                ):
                    issues.append(
                        "Oracle must name a dotted integer metric path and unsigned integer value"
                    )
                    continue
                for number in expected[name]:
                    parsed = observed.get((name, number))
                    if parsed is None or not parsed["contract_valid"]:
                        continue
                    metric = parsed["metrics"].get(path)
                    if (
                        not metric
                        or metric["availability"] != "observed"
                        or type(metric["value"]) is not int
                        or metric["value"] != wanted
                    ):
                        issues.append(
                            "Observability oracle mismatch for {} invocation {}: {} expected {}".format(
                                name, number, path, wanted
                            )
                        )
    result["valid"] = not issues
    result["status"] = "valid" if not issues else "invalid"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--legacy-format", choices=LEGACY_FORMATS)
    options = parser.parse_args(argv)
    result = load_observability(
        options.path,
        expected_sha256=options.expected_sha256,
        legacy_format=options.legacy_format,
    )
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["contract_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
