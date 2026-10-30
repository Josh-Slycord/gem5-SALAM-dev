"""Effective gem5 system option witnesses from raw config and live classes."""
from pathlib import Path
import tempfile
import unittest

from salam_workbench.system_witness import capture_system, witness_system


INI = """[system]
mem_ranges=0:4096
cache_line_size=64
[system.clk_domain]
clock=1000
[system.cpu_clk_domain]
clock=500
[system.cpu]
type=O3CPU
[system.cpu.icache]
type=Cache
size=1024
assoc=2
[system.cpu.dcache]
type=Cache
size=2048
assoc=4
[system.l2]
type=Cache
size=4194304
assoc=8
[system.mem_ctrls.dram]
type=DRAMInterface
ranks_per_channel=2
[system.workload]
dtb_filename=
"""
STATS = "---------- Begin Simulation Statistics ----------\nsimFreq 1000000000000\n---------- End Simulation Statistics ----------\n"


class SystemWitnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ini = Path(self.temp.name) / "config.ini"
        self.stats = Path(self.temp.name) / "stats.txt"
        self.ini.write_text(INI)
        self.stats.write_text(STATS)

    def test_distinct_requested_knobs_match_effective_state(self):
        requested = {
            "mem-size": "4kB", "cpu-type": "DerivO3CPU", "num-cpus": 1,
            "cacheline-size": 64, "caches": True, "l2cache": True,
            "l1i-size": "1kB", "l1d-size": "2kB", "l2-size": "4MB",
            "l1i-assoc": 2, "l1d-assoc": 4, "l2-assoc": 8,
            "sys-clock": "1GHz", "cpu-clock": "2GHz",
            "mem-channels": 1, "mem-ranks": 2,
            "mem-type": "DDR4_2400_8x8",
            "machine-type": "VExpress_GEM5_V1", "dtb-file": "none",
        }
        live = {"dram_classes": ["DDR4_2400_8x8"],
                "platform_class": "VExpress_GEM5_V1"}
        result = witness_system(self.ini, requested, stats_path=self.stats,
                                runtime_system=live)
        self.assertEqual(result["state"], "passed")
        self.assertFalse(result["issues"])
        self.assertFalse(result["unmapped_options"])
        self.assertTrue(all(item["status"] == "passed"
                            for item in result["checks"].values()))

    def test_mismatch_and_unwitnessed_options_remain_distinct(self):
        result = witness_system(
            self.ini, {"mem-size": "8kB", "bare-metal": True,
                       "mem-type": "DDR4_2400_8x8"},
            stats_path=self.stats)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["checks"]["mem-size"]["status"], "failed")
        self.assertEqual(result["checks"]["bare-metal"]["status"], "unwitnessed")
        self.assertEqual(result["checks"]["mem-type"]["status"], "unwitnessed")

    def test_no_cpu_does_not_falsely_satisfy_cache_option(self):
        self.ini.write_text("[system]\nmem_ranges=0:4096\n")
        result = witness_system(self.ini, {"caches": True}, stats_path=self.stats)
        self.assertEqual(result["state"], "failed")

    def test_capture_system_reports_live_classes_without_simulator_imports(self):
        class DDR4_2400_8x8:
            pass

        class MemCtrl:
            dram = DDR4_2400_8x8()

        class VExpress_GEM5_V1:
            pass

        class O3CPU:
            icache = object()
            dcache = object()

        class System:
            cpu = O3CPU()
            mem_ctrls = MemCtrl()
            realview = VExpress_GEM5_V1()

        captured = capture_system(System(), {"mem-type": "DDR4_2400_8x8"})
        self.assertEqual(captured["cpu_classes"], ["O3CPU"])
        self.assertEqual(captured["dram_classes"], ["DDR4_2400_8x8"])
        self.assertEqual(captured["platform_class"], "VExpress_GEM5_V1")


if __name__ == "__main__":
    unittest.main()