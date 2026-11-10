#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Build the SALAM API reference into a new, evidence-preserving directory."""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(argv, *, cwd, env, log):
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    log.with_suffix(".stdout").write_text(result.stdout, encoding="utf-8")
    log.with_suffix(".stderr").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}; see {log}.*")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="new directory; must not already exist",
    )
    parser.add_argument("--doxygen", default="doxygen")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python with Sphinx and Breathe installed",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("output must be outside the source checkout")
    output.mkdir(parents=False, exist_ok=False)
    env = os.environ.copy()
    records = {
        "state": "started",
        "source_root": str(ROOT),
        "output": str(output),
        "doxygen": args.doxygen,
        "python": args.python,
    }
    receipt = output / "build.json"

    def save():
        receipt.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        versions = run(
            [
                args.python,
                "-c",
                "import sphinx, breathe; "
                'print("Sphinx", sphinx.__version__); '
                'print("Breathe", breathe.__version__)',
            ],
            cwd=ROOT,
            env=env,
            log=output / "dependency-check",
        )
        doxygen_version = run(
            [args.doxygen, "--version"],
            cwd=ROOT,
            env=env,
            log=output / "doxygen-version",
        )
        records["tool_versions"] = {
            "python_dependencies": versions.stdout.strip(),
            "doxygen": doxygen_version.stdout.strip(),
        }
        xml = output / "doxygen" / "xml"
        config = (ROOT / "docs" / "Doxyfile.salam").read_text(encoding="utf-8")
        # Later settings override the checked-in defaults, without touching them.
        config += (
            f'\nOUTPUT_DIRECTORY = "{output / "doxygen"}"\n'
            f'WARN_LOGFILE = "{output / "doxygen-warnings.log"}"\n'
            "WARN_AS_ERROR = YES\n"
        )
        config_path = output / "Doxyfile.effective"
        config_path.write_text(config, encoding="utf-8")
        doxygen = run(
            [args.doxygen, str(config_path)], cwd=ROOT, env=env, log=output / "doxygen"
        )
        if "warning:" in doxygen.stderr.lower():
            raise RuntimeError("Doxygen emitted a warning; see doxygen.stderr")
        warnings = output / "doxygen-warnings.log"
        if warnings.exists() and warnings.read_text(encoding="utf-8").strip():
            raise RuntimeError(f"Doxygen warnings remain: {warnings}")
        index = xml / "index.xml"
        tree = ET.parse(index)
        names = {node.text for node in tree.findall("./compound/name")}
        expected = {
            "LLVMInterface",
            "CommInterface",
            "RegisterBank",
            "FUSchedulingPool",
        }
        missing = sorted(expected - names)
        if missing:
            raise RuntimeError(f"Doxygen XML missing expected classes: {missing}")
        env["SALAM_DOXYGEN_XML"] = str(xml)
        run(
            [
                args.python,
                "-m",
                "sphinx",
                "-b",
                "html",
                "-W",
                "--keep-going",
                str(ROOT / "docs"),
                str(output / "html"),
            ],
            cwd=ROOT,
            env=env,
            log=output / "sphinx",
        )
        page = output / "html" / "api" / "cpp" / "index.html"
        text = page.read_text(encoding="utf-8")
        for marker in (
            "LLVMInterface",
            "CommInterface",
            "FUSchedulingPool",
            "RegisterBank",
        ):
            if f'id="class{marker}"' not in text:
                raise RuntimeError(f"HTML missing class declaration: {marker}")
        records.update(
            state="passed",
            xml_classes_checked=sorted(expected),
            html=str(output / "html" / "index.html"),
        )
    except (OSError, RuntimeError, ET.ParseError) as exc:
        records.update(state="failed", error=str(exc))
        save()
        print(str(exc), file=sys.stderr)
        return 1
    save()
    print(f'Built SALAM documentation: {records["html"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
