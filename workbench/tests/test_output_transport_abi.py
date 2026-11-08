"""Native packet-width/overflow controls; real simulated transport is separate."""
import hashlib
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from salam_workbench import benchmark_inputs as inputs
from salam_workbench.benchmark_oracles import make_fixture


class OutputTransportAbiTests(unittest.TestCase):
    def template(self):
        return (inputs.OVERLAYS / "common/workbench_result.h").read_text()

    def native(self, body):
        compiler = shutil.which("g++")
        self.assertIsNotNone(
            compiler, "A host C++ compiler is required for ABI packet controls"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "workbench_input.h").write_text(
                inputs.render_input_header(make_fixture("gemm"))
            )
            (root / "workbench_result.h").write_text(
                inputs.render_result_header(
                    self.template(), inputs.MODERN_WRITEFILE_ABI
                )
            )
            source = root / "packet.cc"
            source.write_text(
                '#include <cstdio>\n#define SALAM_HOST_TEST_WRITEFILE(buffer,length,name) (length)\n#include "workbench_result.h"\nint main() {\n'
                + body
                + "\n}\n"
            )
            binary = root / "packet"
            build = subprocess.run(
                [compiler, "-std=c++11", str(source), "-o", str(binary)],
                capture_output=True,
                timeout=30,
                shell=False,
            )
            self.assertEqual(build.returncode, 0, build.stderr.decode())
            run = subprocess.run(
                [str(binary)], capture_output=True, timeout=10, shell=False
            )
            self.assertEqual(run.returncode, 0, run.stderr.decode())
            return run.stdout

    def test_legacy_default_header_is_byte_exact_and_pinned(self):
        template = self.template()
        self.assertEqual(
            hashlib.sha256(template.encode()).hexdigest(),
            "31e407229f8d837774bdb501deea2fc3b49df8dc76232820e89d4a4af26bb744",
        )
        self.assertEqual(inputs.render_result_header(template), template)
        self.assertIn("alignas(8) uint64_t arguments[5]", template)

    def test_modern_header_uses_five_32bit_slots_and_preserves_wire_serializer(self):
        modern = inputs.render_result_header(
            self.template(), inputs.MODERN_WRITEFILE_ABI
        )
        self.assertIn("alignas(4) uint32_t arguments[5]", modern)
        self.assertIn("sizeof(arguments) == 20", modern)
        self.assertIn("svc #0x5d57", modern)
        self.assertNotIn("uint64_t arguments[5]", modern)
        suffix = "static void salam_result_begin()"
        self.assertEqual(
            modern[modern.index(suffix) :],
            self.template()[self.template().index(suffix) :],
        )

    def test_actual_cpp_packet_bytes_match_v26_slot_offsets(self):
        payload = self.native(
            "uint32_t words[5]; if (!salam_pack_gem5_26_write_arguments(words, 0x12345678ULL, 256, 7, 0x87654321ULL)) return 1; std::fwrite(words, 1, sizeof(words), stdout); return 0;"
        )
        self.assertEqual(len(payload), 20)
        self.assertEqual(
            struct.unpack("<5I", payload), (0x4F00, 0x12345678, 256, 7, 0x87654321)
        )
        self.assertEqual(payload[4:8], bytes.fromhex("78563412"))
        self.assertEqual(payload[16:20], bytes.fromhex("21436587"))

    def test_each_pointer_length_and_offset_overflow_fails_before_cast_or_write(self):
        output = self.native(
            """
            const uint64_t too_wide = 1ULL << 32;
            for (unsigned int field = 0; field < 4; ++field) {
                uint64_t values[4] = {1, 2, 3, 4};
                values[field] = too_wide;
                uint32_t words[5] = {9, 9, 9, 9, 9};
                if (salam_pack_gem5_26_write_arguments(words, values[0], values[1], values[2], values[3])) return 1;
                for (unsigned int i = 0; i < 5; ++i) if (words[i] != 9) return 2;
            }
            return 0;
        """
        )
        self.assertEqual(output, b"")

    def test_32bit_boundary_values_are_not_truncated(self):
        payload = self.native(
            "uint32_t words[5]; if (!salam_pack_gem5_26_write_arguments(words, 0xffffffffULL, 0xffffffffULL, 0xffffffffULL, 0xffffffffULL)) return 1; std::fwrite(words, 1, sizeof(words), stdout); return 0;"
        )
        self.assertEqual(
            struct.unpack("<5I", payload),
            (0x4F00, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF),
        )

    def test_changed_legacy_template_cannot_silently_receive_modern_port(self):
        with self.assertRaisesRegex(ValueError, "source-bound ABI port"):
            inputs.render_result_header(
                self.template().replace("0x4f00", "0x5000"), inputs.MODERN_WRITEFILE_ABI
            )
        with self.assertRaisesRegex(ValueError, "Unsupported result transport ABI"):
            inputs.render_result_header(self.template(), "unknown")

    def source(self, root):
        # Reuse the established fixture factory without importing its TestCase
        # into this module's discovery namespace or executing any of its tests.
        import importlib

        factory = importlib.import_module("test_benchmark_inputs").BenchmarkInputTests(
            "test_all_supported_workloads_preserve_kernels_and_bind_header_identity"
        )
        return factory._source(root, "gemm")

    def test_stage_receipt_binds_explicit_modern_abi_and_real_header_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self.source(root)
            result = inputs.stage_benchmark_inputs(
                root,
                "gemm",
                make_fixture("gemm"),
                output_abi=inputs.MODERN_WRITEFILE_ABI,
            )
            header = base / "sw/workbench_result.h"
            self.assertEqual(
                result["output_transport_abi"], inputs.MODERN_WRITEFILE_ABI
            )
            self.assertEqual(
                result["output_transport_header"]["sha256"],
                hashlib.sha256(header.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                result["output_transport_template_sha256"],
                inputs.LEGACY_RESULT_HEADER_SHA256,
            )
            self.assertIn("uint32_t arguments[5]", header.read_text())

    def test_direct_stage_defaults_to_legacy_regardless_of_active_workspace_profile(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self.source(root)
            result = inputs.stage_benchmark_inputs(root, "gemm", make_fixture("gemm"))
            self.assertEqual(
                result["output_transport_abi"], inputs.LEGACY_WRITEFILE_ABI
            )
            self.assertEqual(
                (base / "sw/workbench_result.h").read_text(), self.template()
            )
