"""Safety and failure-contract tests for isolated hardware generation."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from salam_workbench.hardware_codegen import (
    _FU_CONSTRUCTOR_FIELDS,
    _INST_CONSTRUCTOR_FIELDS,
    FLOAT_FIELDS,
    _class_patch,
    _generator_patch,
    _generated_constructor_contract,
    generate_hardware_code,
)


class HardwareCodegenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = self.root / "engine"
        self.engine.mkdir()
        self.output = self.root / "evidence"

    def test_rejects_unsafe_selection_before_creating_evidence(self):
        with self.assertRaises(ValueError):
            generate_hardware_code(self.engine, "../gemm", self.output)
        self.assertFalse(self.output.exists())

    def test_refuses_to_stage_inside_source_engine(self):
        with self.assertRaises(ValueError):
            generate_hardware_code(self.engine, "gemm", self.engine / "evidence")
        self.assertFalse((self.engine / "evidence").exists())

    def test_missing_generator_retains_failed_receipt(self):
        result = generate_hardware_code(self.engine, "gemm", self.output)
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["valid"])
        self.assertFalse(result["simulation_ready"])
        self.assertIn("HWProfileGenerator.py", result["errors"][0])
        saved = json.loads((self.output / "hardware-codegen.json").read_text())
        self.assertEqual(saved["state"], "failed")
        self.assertFalse((self.engine / "src").exists())

    def test_staged_template_preserves_fu_activity_interface(self):
        source = "\n".join(
            [r"\t" + name + " = Param.UInt32(" for name in FLOAT_FIELDS]
            + [
                "self.inst_dict['instructions'][inst_name]['functional_unit_limit']",
                r'self.base_header_file.write("\t\tuint64_t _in_use;\n\n")',
                r'self.base_header_file.write("\t\tbool is_available() { return (_in_use >= _available); }\n")',
            ]
        )
        patched = _class_patch(source)
        self.assertIn(r"\t\tuint64_t _in_use = 0;", patched)
        self.assertIn("get_in_use() { return _in_use; }", patched)
        self.assertIn(".get('functional_unit_limit', 0)", patched)
        for name in FLOAT_FIELDS:
            self.assertIn(r"\t" + name + " = Param.Float(", patched)

    def test_capable_template_keeps_corrected_capacity_checks(self):
        source = "\n".join(
            [r"\t" + name + " = Param.UInt32(" for name in FLOAT_FIELDS]
            + [
                "self.inst_dict['instructions'][inst_name]['functional_unit_limit']",
                r'self.base_header_file.write("\t\tuint64_t _in_use = 0;\n\n")',
                r'self.base_header_file.write("\t\tuint64_t get_in_use() { return _in_use; }\n")',
                r'self.base_header_file.write("\t\tbool is_available() { return (_available == 0 || _in_use < _available); }\n")',
                "FU occupancy underflow",
            ]
        )
        patched = _class_patch(source, capable=True)
        self.assertIn("_available == 0 || _in_use < _available", patched)
        self.assertEqual(patched.count("get_in_use()"), 1)
        self.assertIn(".get('functional_unit_limit', 0)", patched)
        with self.assertRaisesRegex(ValueError, "exact scheduler repair"):
            _class_patch(
                source.replace(
                    "_available == 0 || _in_use < _available",
                    "_in_use >= _available",
                ),
                capable=True,
            )

    def test_canonical_class_template_accepted_as_is(self):
        source = "\n".join(
            [r"\t" + name + " = Param.Float(" for name in FLOAT_FIELDS]
            + [
                "self.inst_dict['instructions'][inst_name].get('functional_unit_limit', 0)",
                r'self.base_header_file.write("\t\tuint64_t _in_use = 0;\n\n")',
                r'self.base_header_file.write("\t\tuint64_t get_in_use() { return _in_use; }\n")',
                r'self.base_header_file.write("\t\tbool is_available() { return (_available == 0 || _in_use < _available); }\n")',
                "FU occupancy underflow",
            ]
        )
        patched = _class_patch(source, capable=True)
        self.assertEqual(patched, source)

    def test_unexpected_class_template_rejected(self):
        corrupted = "\n".join(
            [r"\t" + FLOAT_FIELDS[0] + " = Param.Float("]
            + [r"\t" + name + " = Param.UInt32(" for name in FLOAT_FIELDS[1:]]
            + ["self.inst_dict['instructions'][inst_name]['functional_unit_limit']"]
        )
        with self.assertRaisesRegex(
            ValueError, "neither recognized legacy nor canonical"
        ):
            _class_patch(corrupted)

    def test_generator_template_legacy_and_canonical_handling(self):
        legacy = (
            "self.fu_list = os.listdir(self.yaml_dir)\n"
            "generate_hw_models = HWModel(benchname=benchmark_args.bench, latency='5ns')\n"
        )
        patched_legacy = _generator_patch(
            legacy, "40nm_model", "5ns", "default_profile"
        )
        self.assertIn("sorted(os.listdir(self.yaml_dir))", patched_legacy)
        self.assertIn(
            "model='40nm_model', latency='5ns', profile='default_profile'",
            patched_legacy,
        )

        canonical = (
            "self.fu_list = sorted(os.listdir(self.yaml_dir))\n"
            "generate_hw_models = HWModel(benchname=benchmark_args.bench, "
            "model=benchmark_args.model, latency=benchmark_args.latency, profile=benchmark_args.profile)\n"
        )
        # Defaults accept as-is
        accepted = _generator_patch(
            canonical, "40nm_model", "5ns", "default_profile"
        )
        self.assertEqual(accepted, canonical)

        # Overrides patch target values
        patched_override = _generator_patch(
            canonical, "28nm_model", "2ns", "fast_profile"
        )
        self.assertIn(
            "model='28nm_model', latency='2ns', profile='fast_profile'",
            patched_override,
        )

        # Unexpected template raises ValueError
        corrupted = "self.fu_list = custom_listing\n"
        with self.assertRaisesRegex(
            ValueError, "neither recognized legacy nor canonical"
        ):
            _generator_patch(corrupted, "40nm_model", "5ns", "default_profile")

    def test_profile_alias_mismatch_stops_before_generator_runs(self):
        for filename in (
            "HWProfileGenerator.py",
            "SALAMClassGenerator.py",
            "SALAMArgs.py",
        ):
            (self.engine / filename).write_text("# fixture source\n")
        profile = (
            self.engine / "benchmarks/sys_validation/gemm/configs/"
            "hw_interface/functional_units/40nm_model/5ns/"
            "default_profile/integer_adder"
        )
        profile.mkdir(parents=True)
        (profile / "integer_adder.yml").write_text(
            "functional_unit:\n  parameters:\n    alias: wrong_unit\n"
        )
        result = generate_hardware_code(self.engine, "gemm", self.output)
        self.assertEqual(result["state"], "failed")
        self.assertIn("alias disagrees", result["errors"][0])
        self.assertFalse((self.output / "generator.stdout").exists())


class ConstructorConsumerTests(unittest.TestCase):
    """Test actual generated sources, including failures hidden by delegation."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stage = Path(self.temp.name)
        self.engine = Path(__file__).resolve().parents[2]
        self.folder = self.stage / "src/hwacc/HWModeling/generated"
        for group, name in (
            ("functionalunits", "double_multiplier"),
            ("instructions", "fmul"),
        ):
            target = self.folder / group
            target.mkdir(parents=True)
            for filename in ("base.hh", name + ".cc"):
                shutil.copyfile(
                    self.engine / "src/hwacc/HWModeling/generated" / group / filename,
                    target / filename,
                )

    def witness(self):
        return _generated_constructor_contract(
            self.stage, ["double_multiplier"], ["fmul"]
        )

    def replace(self, relative, old, new):
        path = self.folder / relative
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1))

    def test_shared_constructor_routes_all_declared_fields(self):
        result = self.witness()
        self.assertEqual(result["state"], "passed")
        self.assertEqual(
            [group["fields"] for group in result["groups"]],
            [list(_FU_CONSTRUCTOR_FIELDS), list(_INST_CONSTRUCTOR_FIELDS)],
        )
        self.assertTrue(
            all(
                group["constructor_forms"] == ["shared_params"]
                for group in result["groups"]
            )
        )

    def test_legacy_expanded_constructor_remains_supported(self):
        for group, name, base, fields in (
            (
                "functionalunits",
                "double_multiplier",
                "FunctionalUnitBase",
                _FU_CONSTRUCTOR_FIELDS,
            ),
            ("instructions", "fmul", "InstConfigBase", _INST_CONSTRUCTOR_FIELDS),
        ):
            self.replace(
                group + "/" + name + ".cc",
                base + "(params)",
                base + "(" + ", ".join("params." + field for field in fields) + ")",
            )
            path = self.folder / group / "base.hh"
            text, count = re.subn(
                r"\s*template <typename Params>\s*explicit "
                + base
                + r"\(const Params &params\)\s*:\s*"
                + base
                + r"\(.*?\) \{ \}",
                "",
                path.read_text(),
                count=1,
                flags=re.S,
            )
            self.assertEqual(count, 1)
            path.write_text(text)
        result = self.witness()
        self.assertTrue(
            all(
                group["constructor_forms"] == ["expanded_params"]
                for group in result["groups"]
            )
        )

    def test_shared_call_without_real_delegate_is_rejected(self):
        self.replace(
            "functionalunits/base.hh",
            "template <typename Params>",
            "// template <typename Params>",
        )
        with self.assertRaisesRegex(ValueError, "absent shared constructor"):
            self.witness()

    def test_swapped_shared_parameters_are_rejected(self):
        self.replace(
            "functionalunits/base.hh",
            "params.area, params.path_delay",
            "params.path_delay, params.area",
        )
        with self.assertRaisesRegex(
            ValueError, "Shared generated constructor fields differ"
        ):
            self.witness()

    def test_wrong_expanded_subclass_argument_is_rejected(self):
        self.replace(
            "instructions/fmul.cc",
            "InstConfigBase(params)",
            "InstConfigBase(params.functional_unit, params.functional_unit_limit, params.runtime_cycles, params.opcode_num)",
        )
        with self.assertRaisesRegex(ValueError, "Generated subclass fields differ"):
            self.witness()

    def test_wrong_final_member_storage_is_rejected(self):
        self.replace("functionalunits/base.hh", "_area(area)", "_area(path_delay)")
        with self.assertRaisesRegex(ValueError, "not stored exactly"):
            self.witness()

    def test_wrong_value_constructor_parameter_order_is_rejected(self):
        self.replace(
            "instructions/base.hh", "uint32_t opcode_num,", "uint32_t swapped_opcode,"
        )
        with self.assertRaisesRegex(ValueError, "field order differs"):
            self.witness()

    def test_fractional_coefficient_parameter_storage_and_getter_are_checked(self):
        path = self.folder / "functionalunits/base.hh"
        original = path.read_text()
        for old, new, message in (
            ("double area,", "uint32_t area,", "coefficient parameter"),
            ("double _area;", "uint32_t _area;", "coefficient storage"),
            ("double get_area()", "uint32_t get_area()", "coefficient getter"),
        ):
            with self.subTest(stage=message):
                self.assertIn(old, original)
                path.write_text(original.replace(old, new, 1))
                with self.assertRaisesRegex(ValueError, message):
                    self.witness()
        path.write_text(original)

    def test_native_common_headers_preserve_values_and_capacity(self):
        # Compile the actual generated headers unchanged. Only the unused power
        # model include is stubbed, keeping this test independent of gem5 builds.
        compiler = shutil.which("g++")
        self.assertIsNotNone(
            compiler, "g++ is required for generated-header consumer tests"
        )
        stub = self.folder.parent / "src/salam_power_model.hh"
        stub.parent.mkdir()
        stub.write_text("#pragma once\n")
        source = self.stage / "consumer.cc"
        source.write_text(
            r"""
#include "src/hwacc/HWModeling/generated/functionalunits/base.hh"
#include "src/hwacc/HWModeling/generated/instructions/base.hh"
#include <cassert>
#include <type_traits>
struct FUParams {
    std::string alias = "fractional-profile";
    uint32_t stages = 2, cycles = 3, enum_value = 5;
    std::string int_size = "i17", int_sign = "unsigned";
    bool int_apmode = true;
    std::string fp_size = "f23", fp_sign = "signed";
    bool fp_apmode = false;
    std::string ptr_size = "p47", ptr_sign = "ptrsigned";
    bool ptr_apmode = true;
    uint32_t limit = 2;
    std::string power_units = "mW", energy_units = "pJ", time_units = "ns", area_units = "um2";
    uint32_t fu_latency = 13;
    double internal_power = 0.125, switch_power = 0.25, dynamic_power = 0.375;
    double dynamic_energy = 0.5, leakage_power = 0.625, area = 7.25, path_delay = 1.125;
};
struct InstParams {
    uint32_t functional_unit = 11, functional_unit_limit = 17, opcode_num = 23, runtime_cycles = 29;
};
int main() {
    FUParams params;
    FunctionalUnitBase fu(params);
    assert(fu.get_alias() == params.alias && fu.get_stages() == 2 && fu.get_cycles() == 3 && fu.get_enum_value() == 5);
    assert(fu.get_int_size() == "i17" && fu.get_int_sign() == "unsigned" && fu.get_int_apmode());
    assert(fu.get_fp_size() == "f23" && fu.get_fp_sign() == "signed" && !fu.get_fp_apmode());
    assert(fu.get_ptr_size() == "p47" && fu.get_ptr_sign() == "ptrsigned" && fu.get_ptr_apmode());
    assert(fu.get_limit() == 2 && fu.get_fu_latency() == 13);
    assert(fu.get_power_units() == "mW" && fu.get_energy_units() == "pJ" && fu.get_time_units() == "ns" && fu.get_area_units() == "um2");
    static_assert(std::is_same_v<decltype(fu.get_internal_power()), double>);
    static_assert(std::is_same_v<decltype(fu.get_switch_power()), double>);
    static_assert(std::is_same_v<decltype(fu.get_dynamic_power()), double>);
    static_assert(std::is_same_v<decltype(fu.get_dynamic_energy()), double>);
    static_assert(std::is_same_v<decltype(fu.get_leakage_power()), double>);
    static_assert(std::is_same_v<decltype(fu.get_area()), double>);
    static_assert(std::is_same_v<decltype(fu.get_path_delay()), double>);
    assert(fu.get_internal_power() == 0.125 && fu.get_switch_power() == 0.25 && fu.get_dynamic_power() == 0.375);
    assert(fu.get_dynamic_energy() == 0.5 && fu.get_leakage_power() == 0.625 && fu.get_area() == 7.25 && fu.get_path_delay() == 1.125);
    assert(fu.get_in_use() == 0 && fu.get_functional_unit_limit() == 2 && fu.is_available());
    fu.use_functional_unit();
    assert(fu.is_available());
    fu.use_functional_unit();
    assert(!fu.is_available());
    fu.clear_functional_unit();
    fu.clear_functional_unit();
    bool underflow = false;
    try { fu.clear_functional_unit(); } catch (const std::logic_error &) { underflow = true; }
    assert(underflow && fu.get_in_use() == 0);
    params.limit = 0;
    FunctionalUnitBase unlimited(params);
    for (int n = 0; n < 8; ++n) { unlimited.use_functional_unit(); assert(unlimited.is_available()); }
    unlimited.set_functional_unit_limit(8);
    assert(!unlimited.is_available());
    unlimited.inc_functional_unit_limit();
    assert(unlimited.is_available() && unlimited.get_functional_unit_limit() == 9);
    InstParams instruction_params;
    InstConfigBase inst(instruction_params);
    assert(inst.get_functional_unit() == 11 && inst.get_functional_unit_limit() == 17);
    assert(inst.get_opcode_num() == 23 && inst.get_runtime_cycles() == 29);
    InstConfigBase defaults;
    assert(defaults.get_functional_unit() == 0 && defaults.get_functional_unit_limit() == 0);
    assert(defaults.get_opcode_num() == 0 && defaults.get_runtime_cycles() == 0);
}
"""
        )
        executable = self.stage / "consumer"
        compiled = subprocess.run(
            [
                compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(source),
                "-o",
                str(executable),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        executed = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=10, check=False
        )
        self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)


if __name__ == "__main__":
    unittest.main()
