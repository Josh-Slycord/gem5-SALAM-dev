import json
import tempfile
import unittest
from pathlib import Path

from salam_workbench.builds import (
    select_receipt,
    selected_receipt,
    verify_receipt,
    write_receipt_new,
)
from salam_workbench.runner import file_hash


class BuildReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="salam-build-receipts-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = self.root / "engine"
        (self.engine / "build/ARM").mkdir(parents=True)
        (self.engine / "build/ARM/gem5.opt").write_bytes(b"synthetic simulator fixture")
        (self.root / "evidence").mkdir()
        (self.root / "evidence/toolchain.json").write_text('{"id":"fixture"}')
        self.receipt = {
            "schema_version": 1,
            "state": "completed",
            "binary_sha256": file_hash(self.engine / "build/ARM/gem5.opt"),
            "engine_source_sha256": "source-fixture",
            "toolchain_sha256": file_hash(self.root / "evidence/toolchain.json"),
        }
        self.old = self.root / "evidence/engine-artifact.json"
        write_receipt_new(self.old, self.receipt)
        (self.root / "workspace.json").write_text('{"engine":{}}')

    def test_old_manifest_fallback_and_new_selection_preserve_old_bytes(self):
        old_bytes = self.old.read_bytes()
        self.assertEqual(selected_receipt(self.root)[0], self.old)
        new = self.root / "evidence/build-v2.json"
        write_receipt_new(new, dict(self.receipt, label="next"))
        self.assertEqual(select_receipt(self.root, new), "evidence/build-v2.json")
        self.assertEqual(selected_receipt(self.root)[0], new)
        self.assertEqual(self.old.read_bytes(), old_bytes)

    def test_existing_receipt_cannot_be_overwritten(self):
        before = self.old.read_bytes()
        with self.assertRaises(FileExistsError):
            write_receipt_new(self.old, {"state": "failed"})
        self.assertEqual(self.old.read_bytes(), before)

    def test_binary_source_and_toolchain_mutations_fail_verification(self):
        verify_receipt(self.root, self.engine, "source-fixture")
        with self.assertRaises(ValueError):
            verify_receipt(self.root, self.engine, "different-source")
        binary = self.engine / "build/ARM/gem5.opt"
        original = binary.read_bytes()
        binary.write_bytes(b"different binary")
        with self.assertRaises(ValueError):
            verify_receipt(self.root, self.engine, "source-fixture")
        binary.write_bytes(original)
        (self.root / "evidence/toolchain.json").write_text('{"id":"changed"}')
        with self.assertRaises(ValueError):
            verify_receipt(self.root, self.engine, "source-fixture")

    def test_external_receipts_and_traversal_are_rejected(self):
        for value in (
            "../receipt.json",
            "/tmp/receipt.json",
            "C:/receipt.json",
            "evidence\\receipt.json",
        ):
            (self.root / "workspace.json").write_text(
                json.dumps({"engine": {"build_receipt": value}})
            )
            with self.subTest(value=value), self.assertRaises(ValueError):
                selected_receipt(self.root)

    def test_failed_receipt_is_not_selected(self):
        failed = self.root / "evidence/failed.json"
        write_receipt_new(failed, dict(self.receipt, state="failed"))
        before = (self.root / "workspace.json").read_bytes()
        with self.assertRaises(ValueError):
            select_receipt(self.root, failed)
        self.assertEqual((self.root / "workspace.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
