import tempfile
import unittest
from pathlib import Path

from salam_workbench.provenance import RUNTIME_FILES, snapshot_tooling, assert_tooling_unchanged


class ToolingSnapshotTests(unittest.TestCase):
    def test_byte_preservation_mutation_rejection_and_no_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "salam_workbench").mkdir()
            for name in RUNTIME_FILES:
                (root / "salam_workbench" / name).write_bytes(b"# fixture\r\n")
            output = root / "snapshot"
            hashes = snapshot_tooling(root, output)
            assert_tooling_unchanged(root, hashes)
            self.assertEqual((output / "salam_workbench/gemm.py").read_bytes(), b"# fixture\r\n")
            (root / "salam_workbench/gemm.py").write_bytes(b"# modified\n")
            with self.assertRaisesRegex(RuntimeError, "changed during experiment"):
                assert_tooling_unchanged(root, hashes)
            with self.assertRaises(FileExistsError):
                snapshot_tooling(root, output)


if __name__ == "__main__":
    unittest.main()
