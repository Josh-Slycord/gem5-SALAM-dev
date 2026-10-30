"""Independent full-output checks for explicitly selected configured inputs.

The saved selector regenerates the complete fixture; neither a recorded pass
nor expected values printed by the guest establish numerical acceptance.
"""
import hashlib
import ast
import json
from pathlib import Path


BENCHMARKS = frozenset(("gemm", "fft", "stencil3d"))


def trace_budget_source_supported(engine):
    path = Path(engine) / "src/hwacc/LLVMInterface.py"
    if not path.is_file():
        return False
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.ClassDef) and node.name == "LLVMInterface":
            return any(isinstance(field, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "fu_trace_event_limit"
                for target in field.targets
            ) for field in node.body)
    return False


def validate_input_case(benchmark, case, *, allow_controls=True):
    if benchmark not in {"benchmarks/sys_validation/" + n for n in BENCHMARKS}:
        raise ValueError("Independent generated inputs require sys_validation GEMM, FFT or stencil3d")
    if not isinstance(case, dict) or set(case) - {
        "dataset", "seed", "inject_mismatch", "force_guest_pass"
    }:
        raise ValueError("Unknown benchmark input fields")
    if case.get("dataset") not in ("seeded", "zeros", "boundary"):
        raise ValueError("Unsupported generated dataset")
    if type(case.get("seed")) is not int or not 0 <= case["seed"] <= 2147483647:
        raise ValueError("Input seed must be an integer from 0 to 2147483647")
    for key in ("inject_mismatch", "force_guest_pass"):
        if key in case and (type(case[key]) is not bool or not allow_controls):
            raise ValueError("Negative controls require explicit backend-only booleans")
    if case.get("force_guest_pass") and not case.get("inject_mismatch"):
        raise ValueError("Forced guest pass requires an intentional output mismatch")
    return dict(case)


def fixture_for_spec(spec):
    from .benchmark_oracles import make_fixture

    case = validate_input_case(spec["benchmark"], spec["benchmark_input"])
    return make_fixture(Path(spec["benchmark"]).name, case["dataset"], case["seed"])


def assess_configured_output(spec, terminal, fixture_path=None):
    """Regenerate expected inputs/results and assess the raw hardware output."""
    from .benchmark_oracles import assess_output, validate_fixture

    fixture = fixture_for_spec(spec)
    if fixture_path is not None:
        saved = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        validate_fixture(saved)
        if saved != fixture:
            raise ValueError("Saved benchmark fixture differs from the requested input")
    terminal = Path(terminal)
    if terminal.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Numerical output exceeds bounded reader limit")
    payload = terminal.read_bytes()
    result = assess_output(payload.decode("utf-8", errors="strict"), fixture)
    result["numerical_output_source"] = str(terminal)
    result["numerical_output_source_sha256"] = hashlib.sha256(payload).hexdigest()
    if terminal.name == "system.terminal":
        result["terminal_sha256"] = hashlib.sha256(payload).hexdigest()
    result["fixture_sha256"] = fixture["fixture_sha256"]
    result["input_case"] = spec["benchmark_input"]
    result["scope"] = "All emitted accelerator output elements versus an independent CPU oracle; fixed shapes with generated inputs"
    return result


def numerical_output_relative(pipeline):
    inputs = pipeline.get("benchmark_inputs", {})
    if not isinstance(inputs, dict):
        raise ValueError("Malformed benchmark input receipt")
    if "output_transport" not in inputs:
        return "simulator/system.terminal"
    transport = inputs["output_transport"]
    if transport != "gem5_semihosting_writefile_text_v1":
        raise ValueError("Unknown configured numerical output transport")
    relative = inputs.get("output_relative")
    if relative != "simulator/salam-results.txt":
        raise ValueError("Configured numerical output path differs from its transport")
    return relative
