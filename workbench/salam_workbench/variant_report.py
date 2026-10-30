"""Evidence-based comparison of the single supported GEMM parameter study."""
import argparse
import configparser
from decimal import Decimal, localcontext
import difflib
import hashlib
import html
import json
from pathlib import Path

from .report import CORE_METRICS, MEASUREMENT_SCOPE, load_run, _link, _normalized_argv
from .runner import file_hash, _safe_relative_path, _safe_run_file

STUDY = {
    "id": "gemm-mul-latency-v1",
    "yaml_path": "hw_config.gemm.instructions.mul.runtime_cycles",
    "effective_section": "system.gemm_clstr.gemm.hw_interface.cycle_counts",
    "effective_key": "mul", "baseline": 1, "variant": 2,
}
CONFIG_RELATIVE = "benchmarks/sys_validation/gemm/config.yml"
PARAMETER = "integer_multiply_latency_cycles"
UNITS = {"simTicks": "tick", "simSeconds": "second", "simInsts": "instruction", "hostSeconds": "second"}
OUTPUT_KEYS = frozenset({"outdir", "output_file", "outfile", "stats_file", "stats_filename",
                         "trace_file", "tracefile", "dump_file", "dump_filename"})


def _json_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _verified_text(run, relative, maximum=16 * 1024 * 1024):
    """Read only a local artifact whose current bytes match the run inventory."""
    relative = _safe_relative_path(relative)
    directory = Path(run["directory"])
    entries = [entry for entry in run["record"].get("artifacts", []) if entry.get("path") == relative]
    if len(entries) != 1 or not _safe_run_file(directory, relative):
        raise ValueError("Missing, duplicate, or unsafe artifact: " + relative)
    path = directory / relative
    if path.stat().st_size > maximum or file_hash(path) != entries[0].get("sha256"):
        raise ValueError("Artifact size/hash verification failed: " + relative)
    return path.read_text(encoding="utf-8"), entries[0]["sha256"]


def _config_input(run):
    inputs = run["record"].get("inputs", [])
    matches = [entry for entry in inputs if str(entry.get("path", "")).replace("\\", "/").endswith("/" + CONFIG_RELATIVE)]
    if len(matches) != 1:
        raise ValueError("Exactly one original GEMM config.yml input is required")
    entry = matches[0]
    snapshot = entry.get("snapshot") or {}
    if (snapshot.get("sha256") != entry.get("sha256") or snapshot.get("unchanged_after_run") is not True
            or snapshot.get("sha256_after_run") != snapshot.get("sha256")):
        raise ValueError("GEMM config input requires a verified, unchanged snapshot")
    text, digest = _verified_text(run, snapshot.get("path", ""), 1024 * 1024)
    if digest != entry["sha256"]:
        raise ValueError("GEMM config snapshot differs from declared input")
    return {"original_path": entry["path"], "snapshot_path": snapshot["path"], "sha256": digest, "text": text}


def _yaml_document(text):
    try:
        import yaml
        from .config import _UniqueLoader
    except ImportError as error:
        raise ValueError("PyYAML and the workbench config loader are required for semantic verification") from error
    try:
        if any(isinstance(token, yaml.tokens.AliasToken) for token in yaml.scan(text)):
            raise ValueError("YAML aliases are unsupported")
        documents = list(yaml.load_all(text, Loader=_UniqueLoader))
    except yaml.YAMLError as error:
        raise ValueError("Invalid or unsupported YAML: " + str(error)) from error
    if len(documents) != 1 or not isinstance(documents[0], dict):
        raise ValueError("Exactly one YAML mapping document is required")
    data = documents[0]
    def supported(value):
        if isinstance(value, dict):
            return all(type(key) is str and supported(item) for key, item in value.items())
        if isinstance(value, list):
            return all(supported(item) for item in value)
        return value is None or type(value) in (str, int, bool)
    if not supported(data):
        raise ValueError("Unsupported YAML scalar type for the fixed GEMM configuration")
    if set(data) != {"acc_cluster", "hw_config"} or not isinstance(data["acc_cluster"], list):
        raise ValueError("Expected the supported acc_cluster/hw_config structure")
    value = data
    for key in STUDY["yaml_path"].split("."):
        if not isinstance(value, dict) or key not in value:
            raise ValueError("Supported multiply latency field is missing")
        value = value[key]
    if type(value) is not int:
        raise ValueError("Multiply latency must be an integer, not a boolean or float")
    return data


def _semantic_diff(a, b, path=""):
    if type(a) is not type(b):
        return [{"path": path, "a": a, "b": b}]
    if isinstance(a, dict):
        result = []
        for key in sorted(set(a) | set(b)):
            child = path + "." + key if path else key
            if key not in a or key not in b:
                result.append({"path": child, "a": a.get(key), "b": b.get(key), "missing_side": "a" if key not in a else "b"})
            else:
                result.extend(_semantic_diff(a[key], b[key], child))
        return result
    if isinstance(a, list):
        if len(a) != len(b):
            return [{"path": path, "a": a, "b": b}]
        return [item for index, pair in enumerate(zip(a, b)) for item in _semantic_diff(pair[0], pair[1], path + "[" + str(index) + "]")]
    return [] if a == b else [{"path": path, "a": a, "b": b}]


def parse_effective_config(text):
    parser = configparser.ConfigParser(interpolation=None, strict=True, delimiters=("=",),
                                       comment_prefixes=("#", ";"), empty_lines_in_values=False)
    parser.optionxform = str
    parser.read_string(text)
    if parser.defaults() or not parser.sections():
        raise ValueError("Effective configuration requires explicit sections and no DEFAULT inheritance")
    return {section: dict(parser.items(section, raw=True)) for section in parser.sections()}


def _normalize_output(value, key, run):
    """Normalize only known output fields beneath this recorded run's outdir."""
    if key not in OUTPUT_KEYS:
        return value
    roots = [str(run["record"].get("run_directory", "")).replace("\\", "/").rstrip("/") + "/simulator"]
    roots += [str(arg).split("=", 1)[1].replace("\\", "/").rstrip("/")
              for arg in run["record"].get("argv", []) if str(arg).startswith("--outdir=")]
    normalized = value.replace("\\", "/")
    for root in roots:
        if root and (normalized == root or normalized.startswith(root + "/")):
            suffix = normalized[len(root):]
            if ".." in suffix.split("/"):
                continue
            return "<run>/simulator" + suffix
    return value


def _effective_comparison(runs):
    maps = []
    hashes = []
    for run in runs:
        text, digest = _verified_text(run, "simulator/config.ini")
        maps.append(parse_effective_config(text))
        hashes.append(digest)
    section, chosen_key = STUDY["effective_section"], STUDY["effective_key"]
    actual = [mapping.get(section, {}).get(chosen_key) for mapping in maps]
    witness = actual == [str(STUDY["baseline"]), str(STUDY["variant"])]
    differences = []
    normalized_maps = [{}, {}]
    for name in sorted(set(maps[0]) | set(maps[1])):
        for index in (0, 1):
            if name in maps[index]:
                normalized_maps[index][name] = {}
        for key in sorted(set(maps[0].get(name, {})) | set(maps[1].get(name, {}))):
            raw = [mapping.get(name, {}).get(key) for mapping in maps]
            normalized = [_normalize_output(value, key, run) if value is not None else None for value, run in zip(raw, runs)]
            if name == section and key == chosen_key:
                classification = "declared_parameter"
                normalized = ["<declared-parameter>", "<declared-parameter>"] if witness else raw
            elif raw != normalized and normalized[0] == normalized[1]:
                classification = "normalized_output_path"
            else:
                classification = "unexpected"
            for index in (0, 1):
                if name in maps[index] and key in maps[index][name]:
                    normalized_maps[index][name][key] = normalized[index]
            if raw[0] != raw[1]:
                differences.append({"section": name, "key": key, "a": raw[0], "b": raw[1], "classification": classification})
    shadow = "system.gemm_clstr.gemm.hw_interface.inst_config.mul"
    return {"artifact_sha256": hashes, "section_count": [len(item) for item in maps],
            "field_count": [sum(len(values) for values in item.values()) for item in maps],
            "normalized_sha256": [_json_hash(item) for item in normalized_maps],
            "other_fields_match": normalized_maps[0] == normalized_maps[1],
            "parameter_witness": {"section": section, "key": chosen_key, "a": actual[0], "b": actual[1], "verified": witness},
            "non_witness": {"section": shadow, "key": "runtime_cycles",
                            "a": maps[0].get(shadow, {}).get("runtime_cycles"),
                            "b": maps[1].get(shadow, {}).get("runtime_cycles"),
                            "note": "inst_config.mul.runtime_cycles may remain 1; it is not the effective multiply-latency witness."},
            "differences": differences,
            "normalization_policy": "Only known output filename fields beneath each recorded run's simulator outdir are normalized; all other sections and keys are compared."}


def _input_map(run, config_path):
    result = {}
    for entry in run["record"].get("inputs", []):
        path = entry["path"]
        if path in result:
            raise ValueError("Duplicate original input path")
        result[path] = entry["sha256"]
    if config_path not in result:
        raise ValueError("Original config input is missing")
    result.pop(config_path)
    if not result:
        raise ValueError("Non-configuration input hashes are required")
    return result


def _normalized_spec(spec):
    result = dict(spec)
    for key in ("experiment_id", "hardware_parameters"):
        result.pop(key, None)
    result["source"] = dict(spec.get("source") or {})
    result["source"].pop("patch_sha256", None)
    return result


def _decimal_text(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def compare_variant_runs(run_a, run_b):
    runs = [load_run(run_a), load_run(run_b)]
    issues, violations, warnings = [], [], []
    invariants = {}
    for run in runs:
        issues.extend(str(run["run_id"]) + ": " + issue for issue in run["issues"])
    if Path(run_a).resolve() == Path(run_b).resolve():
        violations.append("Baseline and variant must be different run directories")
    specs = [run["experiment"] for run in runs]
    records = [run["record"] for run in runs]

    def invariant(name, left, right, required=True):
        match = left == right and (not required or left is not None)
        invariants[name] = {"match": match, "a": left, "b": right}
        if not match:
            violations.append("Invariant differs or is missing: " + name)

    for field in ("workload", "machine", "correctness", "metrics", "environment"):
        invariant("experiment." + field, specs[0].get(field), specs[1].get(field))
    invariant("experiment_except_declared_changes", _normalized_spec(specs[0]), _normalized_spec(specs[1]))
    invariant("parameter_study", specs[0].get("parameter_study"), specs[1].get("parameter_study"))
    if any(spec.get("parameter_study") != STUDY for spec in specs):
        violations.append("Unsupported or altered parameter-study contract")
    for spec, expected in zip(specs, (1, 2)):
        declared = spec.get("hardware_parameters")
        if (not isinstance(declared, dict) or set(declared) != {PARAMETER}
                or type(declared.get(PARAMETER)) is not int or declared[PARAMETER] != expected):
            violations.append("Hardware parameter declaration must be exactly integer multiply latency 1 then 2")
    if not all(spec.get("experiment_id") for spec in specs) or specs[0].get("experiment_id") == specs[1].get("experiment_id"):
        violations.append("Baseline and variant require distinct experiment identifiers")
    patches = [(spec.get("source") or {}).get("patch_sha256") for spec in specs]
    if not all(patches) or patches[0] == patches[1]:
        violations.append("The declared source patch hashes must differ for the config change")
    for field in ("revision", "tree"):
        invariant("source." + field, (specs[0].get("source") or {}).get(field), (specs[1].get("source") or {}).get(field))
    invariant("executable_sha256", (records[0].get("executable") or {}).get("sha256"), (records[1].get("executable") or {}).get("sha256"))
    invariant("argv_except_outdir", _normalized_argv(records[0]), _normalized_argv(records[1]))
    invariant("cwd", records[0].get("cwd"), records[1].get("cwd"))
    invariant("environment", records[0].get("environment"), records[1].get("environment"))
    configuration = None
    try:
        configs = [_config_input(run) for run in runs]
        invariant("original_config_path", configs[0]["original_path"], configs[1]["original_path"])
        invariant("all_input_hashes_except_config", _input_map(runs[0], configs[0]["original_path"]), _input_map(runs[1], configs[1]["original_path"]))
        data = [_yaml_document(config["text"]) for config in configs]
        changes = _semantic_diff(data[0], data[1])
        expected = [{"path": STUDY["yaml_path"], "a": 1, "b": 2}]
        if changes != expected:
            violations.append("YAML semantic difference is not exactly the declared multiply latency 1 to 2")
        configuration = {"inputs": [{key: value for key, value in item.items() if key != "text"} for item in configs],
                         "semantic_differences": changes, "single_declared_change": changes == expected,
                         "text_diff": "".join(difflib.unified_diff(configs[0]["text"].splitlines(keepends=True), configs[1]["text"].splitlines(keepends=True), fromfile="baseline/config.yml", tofile="variant/config.yml")),
                         "parser": "Workbench duplicate-key-rejecting SafeLoader; aliases and multiple documents rejected"}
    except (OSError, ValueError, KeyError, TypeError) as error:
        issues.append("Input configuration verification: " + str(error))
    effective = None
    try:
        effective = _effective_comparison(runs)
        if not effective["parameter_witness"]["verified"]:
            violations.append("Effective cycle_counts.mul does not witness baseline 1 and variant 2")
        if not effective["other_fields_match"]:
            violations.append("Other effective configuration fields differ; a single-parameter interpretation is not established")
        warnings.extend("Normalized run-specific output path: " + item["section"] + "." + item["key"]
                        for item in effective["differences"] if item["classification"] == "normalized_output_path")
        invariants["effective_configuration_except_declared_parameter_and_output_paths"] = {"match": effective["other_fields_match"], "a": effective["normalized_sha256"][0], "b": effective["normalized_sha256"][1]}
    except (OSError, ValueError, KeyError, TypeError, configparser.Error) as error:
        issues.append("Effective configuration verification: " + str(error))

    metric_rows = []
    names = list(CORE_METRICS) + sorted((set(runs[0]["metrics"]) | set(runs[1]["metrics"])) - set(CORE_METRICS))
    for name in names:
        a, b = [run["metrics"].get(name) for run in runs]
        row = {"name": name, "unit": UNITS.get(name, "as emitted; not independently validated"),
               "a": a, "b": b, "delta": None, "percent_change": None,
               "domain": "host" if name == "hostSeconds" else ("simulated" if name in CORE_METRICS else "unvalidated_optional"),
               "observation": None}
        if not a or not b or a["status"] != "present" or b["status"] != "present":
            row["observation"] = "missing or invalid"
            if name in CORE_METRICS:
                issues.append("Required metric is missing or invalid: " + name)
            else:
                warnings.append("Optional metric is missing or invalid: " + name)
        else:
            with localcontext() as context:
                context.prec = 50
                left, right = Decimal(a["value"]), Decimal(b["value"])
                delta = right - left
                row["delta"] = _decimal_text(delta)
                if left != 0:
                    row["percent_change"] = _decimal_text((delta / left * 100).quantize(Decimal("0.000001")))
                else:
                    row["observation"] = "Percent change undefined because baseline is zero"
        metric_rows.append(row)
    outcome = "incomplete" if issues else ("rejected" if violations else "accepted")
    return {"schema_version": 1, "kind": "gem5_parameter_comparison", "accepted": outcome == "accepted",
            "outcome": outcome, "parameter_study": dict(STUDY),
            "parameter_change": {"name": PARAMETER, "unit": "accelerator cycle", "a": 1, "b": 2,
                                 "yaml_path": STUDY["yaml_path"]},
            "configuration": configuration, "effective_configuration": effective,
            "invariants": invariants, "issues": issues, "violations": violations, "warnings": warnings,
            "metrics": metric_rows, "runs": runs, "measurement_scope": MEASUREMENT_SCOPE,
            "percent_precision_decimal_places": 6,
            "interpretation": "Acceptance establishes a documented one-parameter comparison with passing guest correctness. Metric changes are observations over the full window; no accelerator-only speedup or expected direction is asserted.",
            "host_time_note": "hostSeconds is host elapsed time, not a simulated-performance metric or a deterministic acceptance criterion.",
            "provenance_limit": "Recorded source patch hashes may differ for the declared config edit. All declared non-config input hashes and the complete effective configuration are compared; this report does not reconstruct arbitrary source patches from hashes alone."}


def render_variant_html(result, output_dir):
    escape = lambda value: html.escape(str(value), quote=True)
    rows = []
    for metric in result["metrics"]:
        values = [metric[side]["value"] if metric[side] else "missing" for side in ("a", "b")]
        values += [metric["delta"] if metric["delta"] is not None else "unavailable",
                   metric["percent_change"] + "%" if metric["percent_change"] is not None else "unavailable"]
        rows.append("<tr><th>" + escape(metric["name"]) + "<br><small>" + escape(metric["unit"] + "; " + metric["domain"]) + "</small></th>" + "".join("<td>" + escape(value) + "</td>" for value in values) + "</tr>")
    findings = result["issues"] + result["violations"] + result["warnings"]
    finding_html = "<ul>" + "".join("<li>" + escape(value) + "</li>" for value in findings) + "</ul>" if findings else "<p>Both runs passed evidence checks; recorded invariants support the single declared parameter change.</p>"
    sections = []
    for label, run in zip(("Baseline: 1 cycle", "Variant: 2 cycles"), result["runs"]):
        directory = Path(run["directory"])
        links = " · ".join(_link(directory / path, output_dir, name) for path, name in (
            ("run.json", "Run record"), ("experiment.json", "Experiment"),
            ("simulator/config.ini", "Effective configuration"), ("simulator/config.json", "Configuration JSON"),
            ("simulator/system.terminal", "Guest correctness"), ("simulator/stats.txt", "Statistics"),
            ("stdout.txt", "Stdout"), ("stderr.txt", "Stderr")))
        sections.append("<section><h2>" + label + "</h2><p>" + escape(run["run_id"]) + " · recorded state " + escape(run["recorded_state"]) + "</p><p>" + links + "</p><details><summary>Raw evidence checks and provenance</summary><pre>" + escape(json.dumps({"raw_correctness": run["raw_correctness"], "raw_simulator_exit": run["raw_simulator_exit"], "statistics": run["statistics"], "experiment": run["experiment"]}, indent=2)) + "</pre></details></section>")
    configuration = result["configuration"] or {}
    config_links = " · ".join(_link(Path(run["directory"]) / item["snapshot_path"], output_dir, label + " frozen YAML") for label, run, item in zip(("Baseline", "Variant"), result["runs"], configuration.get("inputs", [])))
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SALAM Research Workbench — one parameter</title><style>
body{font:16px/1.6 system-ui,sans-serif;max-width:1100px;margin:3rem auto;padding:0 1.5rem;color:#1b2634;background:#f4f6f8}header,section{background:white;padding:1.7rem;margin:1.2rem 0;border:1px solid #dce2e9;border-radius:10px}h1,h2{line-height:1.25}a{color:#155c9a}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf1f5;padding:1rem}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:.6rem;border-bottom:1px solid #dce2e9;overflow-wrap:anywhere}.scroll{overflow-x:auto}.scope{border-left:4px solid #a46a16;padding-left:1rem}small{font-weight:normal;color:#526172}
</style><main><header><p>SALAM Research Workbench · recorded parameter study</p><h1>Integer multiply latency: 1 → 2 cycles</h1><p>Comparison status: <strong>""" + escape(result["outcome"]) + "</strong></p><p class=\"scope\">" + escape(result["measurement_scope"]) + "</p></header><section><h2>What this comparison establishes</h2>" + finding_html + "<p>" + escape(result["interpretation"]) + "</p><p>" + escape(result["host_time_note"]) + "</p></section><section><h2>Observed results</h2><div class=\"scroll\"><table><thead><tr><th>Metric / unit</th><th>Baseline</th><th>Variant</th><th>Variant − baseline</th><th>Change from baseline</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div><p>Percent changes use the printed baseline value and are rounded to six decimal places. Zero baselines have no percentage.</p></section><section><h2>The exact parameter change</h2><p>" + config_links + "</p><pre>" + escape(configuration.get("text_diff", "Configuration evidence unavailable")) + "</pre><details open><summary>Effective simulator configuration witness</summary><pre>" + escape(json.dumps(result["effective_configuration"], indent=2)) + "</pre></details><p>The effective witness is cycle_counts.mul. The separate inst_config.mul.runtime_cycles may remain 1 and is not used as proof.</p></section><section><h2>Invariants</h2><pre>" + escape(json.dumps(result["invariants"], indent=2)) + "</pre><p>" + escape(result["provenance_limit"]) + "</p></section>" + "".join(sections) + "<section><h2>Machine-readable comparison</h2><p>" + _link(Path(output_dir) / "comparison.json", output_dir, "Comparison JSON with hashes, values, and evidence") + "</p></section></main></html>"


def write_variant_report(run_a, run_b, output_dir):
    result = compare_variant_runs(run_a, run_b)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("comparison.json", "index.html"):
        if (output_dir / name).exists():
            raise FileExistsError(str(output_dir / name))
    (output_dir / "comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output_dir / "index.html").write_text(render_variant_html(result, output_dir), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_a")
    parser.add_argument("run_b")
    parser.add_argument("--output", required=True)
    options = parser.parse_args()
    result = write_variant_report(options.run_a, options.run_b, options.output)
    print(json.dumps({"outcome": result["outcome"], "output": str(Path(options.output).resolve())}))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
