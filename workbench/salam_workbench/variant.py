"""One predeclared GEMM hardware-parameter experiment, with baseline restoration."""
import argparse
import datetime
import difflib
import hashlib
import json
import re
import uuid
from pathlib import Path

from . import gemm
from .builds import selected_receipt, verify_receipt
from .provenance import assert_tooling_unchanged, snapshot_tooling
from .runner import file_hash
from .variant_report import write_variant_report

STUDY = {
    "id": "gemm-mul-latency-v1",
    "yaml_path": "hw_config.gemm.instructions.mul.runtime_cycles",
    "effective_section": "system.gemm_clstr.gemm.hw_interface.cycle_counts",
    "effective_key": "mul",
    "baseline": 1,
    "variant": 2,
}


def latency_variant(original):
    """Change exactly the existing mul block's latency, preserving other bytes."""
    text = original.decode("utf-8")
    pattern = (
        r"(?m)(^      mul:\n(?:        [^\n]+\n)*?        runtime_cycles: )1(?=\n)"
    )
    changed, count = re.subn(pattern, r"\g<1>2", text)
    if count != 1:
        raise ValueError("Expected exactly one baseline mul.runtime_cycles: 1")
    return changed.encode("utf-8")


def source_identity(engine, session, label, tooling_hashes):
    patch = gemm.git(engine, "diff", "--binary", gemm.BASELINE)
    (session / (label + "-engine.patch")).write_bytes(patch)
    return {
        "recovered_baseline": gemm.BASELINE,
        "revision": gemm.git(engine, "rev-parse", "HEAD").decode().strip(),
        "tree": gemm.git(engine, "rev-parse", "HEAD^{tree}").decode().strip(),
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "engine_build_receipt_sha256": file_hash(selected_receipt(gemm.PROJECT)[0]),
        "engine_features": selected_receipt(gemm.PROJECT)[1].get("features", []),
        "tooling_sha256": tooling_hashes,
        "tooling_snapshot_directory": str(session / "tooling-snapshot"),
    }


def parameter_experiment(engine, source, latency):
    data = gemm.spec(engine, source)
    data["experiment_id"] = "gemm-int32-8x8-mul-latency-" + str(latency)
    data["parameter_study"] = STUDY
    data["hardware_parameters"] = {"integer_multiply_latency_cycles": latency}
    return data


def run_study(engine, runs_root):
    engine, runs_root = (
        Path(engine).resolve(strict=True),
        Path(runs_root).resolve(),
    )
    gemm.git(engine, "merge-base", "--is-ancestor", gemm.BASELINE, "HEAD")
    config = engine / gemm.REL / "config.yml"
    original = config.read_bytes()
    reference = gemm.git(
        engine, "show", gemm.BASELINE + ":" + str(gemm.REL / "config.yml")
    )
    if original != reference:
        raise ValueError(
            "M2 requires the unmodified recovered baseline config; refusing to replace other work"
        )
    variant = latency_variant(original)
    identifier = (
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    session = gemm.PROJECT / "evidence" / ("m2-" + identifier)
    session.mkdir(exist_ok=False)
    (session / "baseline-config.yml").write_bytes(original)
    (session / "variant-config.yml").write_bytes(variant)
    (session / "parameter.patch").write_text(
        "".join(
            difflib.unified_diff(
                original.decode().splitlines(True),
                variant.decode().splitlines(True),
                fromfile="baseline/config.yml",
                tofile="variant/config.yml",
            )
        )
    )
    summary = {
        "schema_version": 1,
        "state": "running",
        "session_directory": str(session),
        "parameter_study": STUDY,
        "runs": [],
        "baseline_configuration_restored": False,
    }
    gemm.save(session / "session.json", summary)
    try:
        tooling_hashes = snapshot_tooling(gemm.PROJECT, session / "tooling-snapshot")
        receipt_path, receipt = verify_receipt(
            gemm.PROJECT, engine, gemm.engine_source_digest(engine)
        )
        for label, latency, payload in [
            ("baseline", 1, original),
            ("variant", 2, variant),
        ]:
            if config.read_bytes() not in (original, variant):
                raise RuntimeError(
                    "Configuration was changed externally; refusing to overwrite"
                )
            config.write_bytes(payload)
            gemm.prepare(engine, session / (label + "-preparation"))
            if config.read_bytes() != payload:
                raise RuntimeError(
                    "Preparation changed the declared parameter configuration"
                )
            if receipt["binary_sha256"] != file_hash(
                engine / "build/ARM/gem5.opt"
            ) or receipt["engine_source_sha256"] != gemm.engine_source_digest(engine):
                raise RuntimeError(
                    "Simulator or engine source changed during experiment preparation"
                )
            assert_tooling_unchanged(gemm.PROJECT, tooling_hashes)
            source = source_identity(engine, session, label, tooling_hashes)
            gemm.save(session / (label + "-source.json"), source)
            record = gemm.execute(
                engine,
                runs_root,
                parameter_experiment(engine, source, latency),
                str(gemm.REL / "sw/main.elf"),
            )
            summary["runs"].append(
                {
                    "role": label,
                    "latency": latency,
                    "state": record["state"],
                    "directory": record["run_directory"],
                }
            )
            gemm.save(session / "session.json", summary)
            print(
                label
                + " mul="
                + str(latency)
                + ": "
                + record["state"]
                + " "
                + record["run_directory"],
                flush=True,
            )
            if record["state"] != "passed":
                raise RuntimeError(
                    label + " failed; retained evidence must be inspected"
                )
        comparison = write_variant_report(
            summary["runs"][0]["directory"],
            summary["runs"][1]["directory"],
            session / "report",
        )
        summary["comparison"] = comparison
        assert_tooling_unchanged(gemm.PROJECT, tooling_hashes)
        summary["state"] = "passed" if comparison["accepted"] else "failed"
        if not comparison["accepted"]:
            raise RuntimeError(
                "Parameter comparison did not meet the declared invariant checks"
            )
    except Exception as error:
        summary["state"] = "failed"
        summary["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        try:
            if config.read_bytes() in (original, variant):
                config.write_bytes(original)
                summary["baseline_configuration_restored"] = (
                    config.read_bytes() == original
                )
            else:
                summary[
                    "restore_error"
                ] = "Unexpected external config change; original saved in session, current bytes preserved"
        except OSError as error:
            summary["restore_error"] = type(error).__name__ + ": " + str(error)
        if not summary["baseline_configuration_restored"]:
            summary["state"] = "failed"
            summary.setdefault(
                "restore_error",
                "Baseline configuration restoration did not verify",
            )
        summary["finished_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        gemm.save(session / "session.json", summary)
        print("Parameter study evidence: " + str(session), flush=True)
    if not summary["baseline_configuration_restored"]:
        raise RuntimeError(summary["restore_error"])
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine", type=Path, required=True)
    p.add_argument("--runs-root", type=Path, default=gemm.PROJECT / "runs")
    a = p.parse_args()
    run_study(a.engine, a.runs_root)


if __name__ == "__main__":
    main()
