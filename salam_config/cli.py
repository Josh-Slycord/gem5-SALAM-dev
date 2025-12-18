#!/usr/bin/env python3
"""
gem5-SALAM Configuration CLI

Main command-line interface for the unified configuration system.
Provides commands for configuration generation, validation, and management.
"""

import argparse
import sys
import os
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports when running as script
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from salam_config.core.logging_config import SALAMLogger, get_logger
from salam_config.core.exceptions import (
    SALAMConfigError,
    ValidationError,
    InvalidCycleTimeError,
)

logger = get_logger("cli")

SUPPORTED_CYCLE_TIMES = ["1ns", "2ns", "3ns", "4ns", "5ns", "6ns", "10ns"]


def cmd_generate(args):
    """Generate all configurations for a benchmark."""
    logger.info(f"Generating configurations for benchmark: {args.benchmark}")

    try:
        from salam_config.core.config_manager import ConfigManager

        mgr = ConfigManager(verbose=args.verbose)
        result = mgr.generate_all(
            benchmark=args.benchmark,
            bench_dir=args.bench_dir,
            cycle_time=args.cycle_time,
            base_address=int(args.base_address, 16)
            if args.base_address.startswith("0x")
            else int(args.base_address),
            dry_run=args.dry_run,
        )

        if result.success:
            logger.info("Configuration generation complete!")
            for output_file in result.generated_files:
                print(f"  Generated: {output_file}")
            return 0
        else:
            logger.error(f"Generation failed: {result.error}")
            return 1

    except SALAMConfigError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def cmd_generate_hw(args):
    """Generate hardware profile C++ classes."""
    logger.info(f"Generating HW profile for benchmark: {args.benchmark}")
    logger.info(
        f"  Model: {args.model}, Latency: {args.latency}, Profile: {args.profile}"
    )

    try:
        from salam_config.generators.hw_profile_generator import HWProfileGenerator

        generator = HWProfileGenerator(
            benchmark=args.benchmark,
            bench_dir=args.bench_dir,
            model=args.model,
            latency=args.latency,
            profile=args.profile,
        )

        result = generator.generate()

        if result.success:
            logger.info("HW profile generation complete!")
            for output_file in result.generated_files:
                print(f"  Generated: {output_file}")
            return 0
        else:
            logger.error(f"Generation failed: {result.error}")
            return 1

    except SALAMConfigError as e:
        logger.error(str(e))
        return 1
    except ImportError:
        # Fall back to placeholder if generator not yet implemented
        logger.warning("HW profile generator not yet fully implemented")
        logger.info("Using power model database for configuration")

        from salam_config.models.power_model import get_power_model

        pm = get_power_model()
        logger.info(f"Power model loaded: {pm.technology_node}")
        logger.info(f"Available FUs: {', '.join(pm.list_functional_units())}")

        # Show timing data for requested latency
        for fu_name in pm.list_functional_units():
            try:
                timing = pm.get_timing(fu_name, args.latency)
                print(
                    f"  {fu_name}: area={timing.area:.2f} um^2, power={timing.dyn_power:.4f} mW"
                )
            except Exception:
                pass

        return 0
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1


def cmd_validate(args):
    """Validate a configuration YAML file."""
    logger.info(f"Validating configuration: {args.config}")

    try:
        from salam_config.core.schema_validator import validate_config_file

        result = validate_config_file(args.config)

        if result.is_valid:
            print(f"Configuration is valid: {args.config}")
            if result.warnings:
                print("\nWarnings:")
                for warning in result.warnings:
                    print(f"  - {warning}")
            return 0
        else:
            print(f"Configuration is INVALID: {args.config}")
            print("\nErrors:")
            for error in result.errors:
                print(f"  - {error}")
            if result.warnings:
                print("\nWarnings:")
                for warning in result.warnings:
                    print(f"  - {warning}")
            return 1

    except SALAMConfigError as e:
        logger.error(str(e))
        return 1
    except ImportError:
        # Validator not yet implemented
        logger.warning("Schema validator not yet fully implemented")

        # Basic YAML validation
        import yaml

        try:
            with open(args.config, "r") as f:
                config = yaml.safe_load(f)

            if "acc_cluster" in config:
                print(f"Configuration appears valid (basic check): {args.config}")
                print(f"  Found acc_cluster section")
                return 0
            else:
                print(f"Configuration may be invalid: missing acc_cluster section")
                return 1
        except yaml.YAMLError as e:
            print(f"YAML parsing error: {e}")
            return 1
        except FileNotFoundError:
            print(f"File not found: {args.config}")
            return 1


def cmd_list_fus(args):
    """List available functional units with power data."""
    try:
        from salam_config.models.power_model import get_power_model

        pm = get_power_model()
        cycle_time = args.cycle_time

        print(f"\nFunctional Units ({pm.technology_node}, {cycle_time}):")
        print("=" * 80)
        print(
            f"{'Name':<25} {'Enum':<6} {'Cycles':<8} {'Area (um^2)':<12} {'Power (mW)':<12}"
        )
        print("-" * 80)

        for fu_name in pm.list_functional_units():
            fu = pm.get_functional_unit(fu_name)
            try:
                timing = fu.get_timing(cycle_time)
                print(
                    f"{fu_name:<25} {fu.enum_value:<6} {fu.default_cycles:<8} {timing.area:<12.2f} {timing.dyn_power:<12.4f}"
                )
            except Exception:
                print(
                    f"{fu_name:<25} {fu.enum_value:<6} {fu.default_cycles:<8} {'N/A':<12} {'N/A':<12}"
                )

        print("")
        return 0

    except Exception as e:
        logger.error(f"Error listing functional units: {e}")
        return 1


def cmd_list_instructions(args):
    """List instruction to functional unit mapping."""
    try:
        from salam_config.models.power_model import get_power_model

        pm = get_power_model()

        print("\nInstruction to Functional Unit Mapping:")
        print("=" * 60)

        # Group by functional unit
        fu_instructions = {}
        for inst in pm.list_instructions():
            fu = pm.get_functional_unit_for_instruction(inst)
            if fu not in fu_instructions:
                fu_instructions[fu] = []
            fu_instructions[fu].append(inst)

        for fu, instructions in sorted(fu_instructions.items()):
            print(f"\n{fu}:")
            print(f"  {', '.join(sorted(instructions))}")

        print("")
        return 0

    except Exception as e:
        logger.error(f"Error listing instructions: {e}")
        return 1


def cmd_info(args):
    """Show information about the configuration system."""
    try:
        from salam_config import __version__
        from salam_config.models.power_model import get_power_model

        print("\ngem5-SALAM Configuration System")
        print("=" * 40)
        print(f"Version: {__version__}")

        # Check M5_PATH
        m5_path = os.environ.get("M5_PATH", "Not set")
        print(f"M5_PATH: {m5_path}")

        # Power model info
        try:
            pm = get_power_model()
            print(f"Technology Node: {pm.technology_node}")
            print(f"Supported Cycle Times: {', '.join(SUPPORTED_CYCLE_TIMES)}")
            print(f"Functional Units: {len(pm.list_functional_units())}")
            print(f"Instructions Mapped: {len(pm.list_instructions())}")
        except Exception as e:
            print(f"Power model: Error loading ({e})")

        print("")
        return 0

    except Exception as e:
        logger.error(f"Error: {e}")
        return 1


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="gem5-SALAM Configuration Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate all configs for a benchmark
  python -m salam_config.cli generate -b gemm

  # Generate HW profile with specific cycle time
  python -m salam_config.cli generate-hw -b bfs -l 10ns

  # Validate a configuration file
  python -m salam_config.cli validate -c benchmarks/sys_validation/gemm/config.yml

  # List functional units
  python -m salam_config.cli list-fus --cycle-time 5ns

  # Show system info
  python -m salam_config.cli info
""",
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # generate command
    gen_parser = subparsers.add_parser(
        "generate", help="Generate all configurations for a benchmark"
    )
    gen_parser.add_argument("-b", "--benchmark", required=True, help="Benchmark name")
    gen_parser.add_argument(
        "-d",
        "--bench-dir",
        default="benchmarks/sys_validation",
        help="Benchmark directory (default: benchmarks/sys_validation)",
    )
    gen_parser.add_argument(
        "--cycle-time",
        default="5ns",
        choices=SUPPORTED_CYCLE_TIMES,
        help="Cycle time (default: 5ns)",
    )
    gen_parser.add_argument(
        "--base-address",
        default="0x10020000",
        help="Base memory address (default: 0x10020000)",
    )
    gen_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without creating files",
    )
    gen_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    gen_parser.set_defaults(func=cmd_generate)

    # generate-hw command
    hw_parser = subparsers.add_parser(
        "generate-hw", help="Generate HW profile C++ classes"
    )
    hw_parser.add_argument("-b", "--benchmark", required=True, help="Benchmark name")
    hw_parser.add_argument(
        "--model", default="40nm_model", help="Technology model (default: 40nm_model)"
    )
    hw_parser.add_argument(
        "-l",
        "--latency",
        default="5ns",
        choices=SUPPORTED_CYCLE_TIMES,
        help="Cycle time (default: 5ns)",
    )
    hw_parser.add_argument(
        "--profile",
        default="default_profile",
        help="Profile name (default: default_profile)",
    )
    hw_parser.add_argument(
        "--bench-dir", default="benchmarks/sys_validation", help="Benchmark directory"
    )
    hw_parser.set_defaults(func=cmd_generate_hw)

    # validate command
    val_parser = subparsers.add_parser("validate", help="Validate configuration YAML")
    val_parser.add_argument(
        "-c", "--config", required=True, help="Path to configuration YAML file"
    )
    val_parser.set_defaults(func=cmd_validate)

    # list-fus command
    list_fus_parser = subparsers.add_parser("list-fus", help="List functional units")
    list_fus_parser.add_argument(
        "--cycle-time",
        default="5ns",
        choices=SUPPORTED_CYCLE_TIMES,
        help="Cycle time for power data (default: 5ns)",
    )
    list_fus_parser.set_defaults(func=cmd_list_fus)

    # list-instructions command
    list_inst_parser = subparsers.add_parser(
        "list-instructions", help="List instruction mappings"
    )
    list_inst_parser.set_defaults(func=cmd_list_instructions)

    # info command
    info_parser = subparsers.add_parser("info", help="Show system information")
    info_parser.set_defaults(func=cmd_info)

    args = parser.parse_args()

    # Set up logging level
    if args.verbose:
        SALAMLogger().set_console_level("DEBUG")

    # Run command
    if hasattr(args, "func"):
        sys.exit(args.func(args))
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
