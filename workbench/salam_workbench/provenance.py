"""Immutable snapshots of the Python code used to execute and assess a study."""
from pathlib import Path

from .runner import file_hash

RUNTIME_FILES = (
    "__init__.py", "runner.py", "config.py", "facade.py", "builds.py",
    "gemm.py", "report.py", "observability.py", "observability_report.py",
    "variant.py", "variant_report.py", "provenance.py",
)


def snapshot_tooling(project, directory):
    project, directory = Path(project).resolve(), Path(directory)
    directory.mkdir(exist_ok=False)
    hashes = {}
    for name in RUNTIME_FILES:
        relative = "salam_workbench/" + name
        source = project / relative
        payload = source.read_bytes()
        target = directory / relative
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(payload)
        hashes[relative] = file_hash(target)
    assert_tooling_unchanged(project, hashes)
    return hashes


def assert_tooling_unchanged(project, hashes):
    """Reject code edits during a study instead of silently rebinding versions."""
    for relative, expected in hashes.items():
        if file_hash(Path(project) / relative) != expected:
            raise RuntimeError("Tooling source changed during experiment: " + relative)
