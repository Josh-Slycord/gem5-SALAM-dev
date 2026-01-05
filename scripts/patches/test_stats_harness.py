#!/usr/bin/env python3
# ==============================================================================
# test_stats_harness.py - Test Harness for gem5-SALAM Statistics System
# ==============================================================================
"""Test harness for verifying the enhanced statistics system.

This module provides:
1. Unit tests for enhanced_stats_parser
2. Mock data generators for testing GUI without running gem5
3. Validation tests for JSON output format
4. ZeroMQ message emulator for testing live stats

Usage:
    # Run all tests
    python3 test_stats_harness.py

    # Run specific test category
    python3 test_stats_harness.py --parser
    python3 test_stats_harness.py --mock
    python3 test_stats_harness.py --emulator

Requirements:
    - Python 3.8+
    - PyZMQ (for emulator tests)
"""

__version__ = "1.0.0"

import json
import sys
import time
import random
import argparse
from pathlib import Path
from dataclasses import asdict

# Add salam_gui to path
SCRIPT_DIR = Path(__file__).parent
SALAM_GUI_DIR = SCRIPT_DIR / "salam_gui"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def generate_mock_stats() -> dict:
    """Generate mock statistics for testing."""
    return {
        "salam_stats": {
            "version": "3.0",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "accelerator_name": "test_accelerator",
            "performance": {
                "setup_time_ns": random.uniform(100, 1000),
                "sim_time_ns": random.uniform(10000, 100000),
                "clock_period_ns": 1,
                "sys_clock_ghz": 1.0,
                "total_cycles": random.randint(10000, 100000),
                "stall_cycles": random.randint(1000, 10000),
                "executed_nodes": random.randint(5000, 50000),
            },
            "memory_access": {
                "cache_hits": random.randint(1000, 10000),
                "cache_misses": random.randint(100, 1000),
                "cache_read_hits": random.randint(500, 5000),
                "cache_read_misses": random.randint(50, 500),
                "cache_write_hits": random.randint(500, 5000),
                "cache_write_misses": random.randint(50, 500),
                "spm_reads": random.randint(1000, 5000),
                "spm_writes": random.randint(500, 2500),
                "dma_reads": random.randint(10, 100),
                "dma_writes": random.randint(10, 100),
                "avg_read_latency": random.uniform(10, 100),
                "avg_write_latency": random.uniform(15, 150),
                "max_read_latency": random.randint(100, 1000),
                "max_write_latency": random.randint(150, 1500),
                "read_port_contentions": random.randint(0, 100),
                "write_port_contentions": random.randint(0, 100),
            },
            "dataflow": {
                "critical_path_length": random.randint(100, 1000),
                "critical_path_instructions": random.randint(50, 500),
                "critical_path_loads": random.randint(10, 100),
                "critical_path_stores": random.randint(10, 100),
                "critical_path_computes": random.randint(30, 300),
                "avg_ready_instructions": random.uniform(1, 10),
                "avg_issued_per_cycle": random.uniform(0.5, 5),
                "max_parallel_ops": random.randint(2, 16),
                "total_instructions": random.randint(5000, 50000),
                "true_dependencies": random.randint(1000, 10000),
                "anti_dependencies": random.randint(100, 1000),
                "output_dependencies": random.randint(50, 500),
                "control_dependencies": random.randint(10, 100),
                "memory_dependencies": random.randint(100, 1000),
                "avg_dependency_depth": random.uniform(2, 10),
                "max_dependency_depth": random.randint(5, 50),
                "total_dependency_edges": random.randint(2000, 20000),
            },
            "stall_breakdown": {
                "total_stalls": random.randint(1000, 10000),
                "no_stall_cycles": random.randint(5000, 50000),
                "memory_latency": random.randint(100, 1000),
                "raw_hazard": random.randint(200, 2000),
                "waw_hazard": random.randint(10, 100),
                "war_hazard": random.randint(50, 500),
                "fu_contention": random.randint(100, 1000),
                "port_contention": random.randint(50, 500),
                "control_flow": random.randint(10, 100),
                "dma_pending": random.randint(5, 50),
                "resource_limit": random.randint(20, 200),
            },
            "power": {
                "fu_leakage": random.uniform(0.001, 0.01),
                "fu_dynamic": random.uniform(0.01, 0.1),
                "fu_total": random.uniform(0.02, 0.15),
                "reg_leakage": random.uniform(0.0005, 0.005),
                "reg_dynamic": random.uniform(0.005, 0.05),
                "reg_total": random.uniform(0.01, 0.1),
                "spm_leakage": random.uniform(0.001, 0.01),
                "spm_total": random.uniform(0.01, 0.1),
                "cache_leakage": random.uniform(0.002, 0.02),
                "cache_total": random.uniform(0.02, 0.2),
                "total_leakage": random.uniform(0.01, 0.1),
                "total_dynamic": random.uniform(0.1, 1.0),
                "total_power": random.uniform(0.2, 2.0),
                "total_energy_nj": random.uniform(100, 10000),
            },
            "area": {
                "fu_area_um2": random.uniform(1000, 10000),
                "reg_area_um2": random.uniform(500, 5000),
                "spm_area_um2": random.uniform(2000, 20000),
                "cache_area_um2": random.uniform(5000, 50000),
                "total_area_um2": random.uniform(10000, 100000),
                "total_area_mm2": random.uniform(0.01, 0.1),
            },
        }
    }


def test_parser():
    """Test the enhanced_stats_parser module."""
    print("=" * 60)
    print("Testing Enhanced Stats Parser")
    print("=" * 60)

    try:
        from salam_gui.data.enhanced_stats_parser import (
            parse_enhanced_json,
            EnhancedSimulationStats,
            format_metric,
            format_percentage,
            format_cycles,
        )

        print("[PASS] Import successful")
    except ImportError as e:
        print(f"[FAIL] Import failed: {e}")
        return False

    # Test parsing mock data
    mock_data = generate_mock_stats()
    json_str = json.dumps(mock_data)

    try:
        stats = parse_enhanced_json(json_str)
        print(f"[PASS] Parsed mock data: {stats.performance.accelerator_name}")
    except Exception as e:
        print(f"[FAIL] Parse failed: {e}")
        return False

    # Verify fields are populated
    checks = [
        ("version", stats.version == "3.0"),
        (
            "accelerator_name",
            stats.performance.accelerator_name == "test_accelerator",
        ),
        ("total_cycles > 0", stats.performance.total_cycles > 0),
        ("cache_hits > 0", stats.memory_access.cache_hits > 0),
        ("critical_path_length > 0", stats.dataflow.critical_path_length > 0),
        ("total_stalls > 0", stats.stall_breakdown.total_stalls > 0),
        ("total_power > 0", stats.power.total_power > 0),
        ("total_area_um2 > 0", stats.area.total_area_um2 > 0),
    ]

    all_pass = True
    for name, result in checks:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")
        if not result:
            all_pass = False

    # Test formatting functions
    print("\nTesting format functions:")
    print(f"  format_cycles(1500000) = {format_cycles(1500000)}")
    print(f"  format_metric(0.0015, 'W') = {format_metric(0.0015, 'W')}")
    print(f"  format_percentage(23.456) = {format_percentage(23.456)}")

    # Test computed properties
    print("\nTesting computed properties:")
    print(f"  cache_hit_rate = {stats.memory_access.cache_hit_rate:.2f}%")
    print(f"  ILP = {stats.dataflow.ilp:.2f}")
    print(
        f"  stall_percentages = {list(stats.stall_breakdown.get_stall_percentages().keys())[:3]}..."
    )

    return all_pass


def test_json_schema():
    """Test that generated JSON matches expected schema."""
    print("=" * 60)
    print("Testing JSON Schema Validation")
    print("=" * 60)

    mock_data = generate_mock_stats()

    # Required top-level keys
    required_keys = ["salam_stats"]
    stats_keys = [
        "version",
        "timestamp",
        "accelerator_name",
        "performance",
        "memory_access",
        "dataflow",
        "stall_breakdown",
        "power",
        "area",
    ]

    all_pass = True

    # Check top level
    for key in required_keys:
        if key in mock_data:
            print(f"[PASS] Top-level key: {key}")
        else:
            print(f"[FAIL] Missing top-level key: {key}")
            all_pass = False

    # Check salam_stats keys
    salam_stats = mock_data.get("salam_stats", {})
    for key in stats_keys:
        if key in salam_stats:
            print(f"[PASS] Stats key: {key}")
        else:
            print(f"[FAIL] Missing stats key: {key}")
            all_pass = False

    return all_pass


def run_zmq_emulator(port: int = 5555, duration: int = 30):
    """Run a ZeroMQ publisher emulator for testing live stats."""
    print("=" * 60)
    print(f"Starting ZeroMQ Stats Emulator on port {port}")
    print(f"Duration: {duration} seconds")
    print("=" * 60)

    try:
        import zmq
    except ImportError:
        print("[ERROR] PyZMQ not installed. Run: pip install pyzmq")
        return

    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind(f"tcp://*:{port}")

    print(f"Publishing to tcp://*:{port}")
    print("Press Ctrl+C to stop\n")

    cycle = 0
    start_time = time.time()

    try:
        # Send simulation start message
        start_msg = {
            "type": "sim_start",
            "cycle": 0,
            "data": {
                "name": "test_simulation",
                "benchmark": "matmul",
                "config": "default",
            },
            "timestamp": time.time(),
        }
        socket.send_string(json.dumps(start_msg))
        print("Sent: sim_start")

        while time.time() - start_time < duration:
            cycle += random.randint(100, 1000)

            # Send cycle update
            cycle_msg = {
                "type": "cycle_update",
                "cycle": cycle,
                "timestamp": time.time(),
            }
            socket.send_string(json.dumps(cycle_msg))

            # Periodically send stats update
            if random.random() < 0.1:
                stats = generate_mock_stats()
                stats["salam_stats"]["performance"]["total_cycles"] = cycle
                stats_msg = {
                    "type": "stats_update",
                    "cycle": cycle,
                    "data": stats["salam_stats"],
                    "timestamp": time.time(),
                }
                socket.send_string(json.dumps(stats_msg))
                print(f"Cycle {cycle}: Sent stats_update")

            time.sleep(0.1)

        # Send simulation end message
        end_msg = {
            "type": "sim_end",
            "cycle": cycle,
            "data": {"total_cycles": cycle},
            "timestamp": time.time(),
        }
        socket.send_string(json.dumps(end_msg))
        print("Sent: sim_end")

    except KeyboardInterrupt:
        print("\nStopping emulator...")
    finally:
        socket.close()
        context.term()
        print("Emulator stopped.")


def save_sample_json(output_path: Path):
    """Save a sample JSON stats file for testing."""
    mock_data = generate_mock_stats()

    # Make it pretty-printed
    with open(output_path, "w") as f:
        json.dump(mock_data, f, indent=2)

    print(f"Sample stats saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Test harness for gem5-SALAM statistics system"
    )
    parser.add_argument(
        "--parser", action="store_true", help="Run parser tests"
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Run JSON schema validation tests",
    )
    parser.add_argument(
        "--emulator", action="store_true", help="Run ZeroMQ stats emulator"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5555,
        help="Port for ZeroMQ emulator (default: 5555)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Duration for emulator in seconds (default: 30)",
    )
    parser.add_argument(
        "--save-sample", type=str, help="Save sample JSON to file"
    )
    parser.add_argument("--all", action="store_true", help="Run all tests")

    args = parser.parse_args()

    # Default to --all if no specific test selected
    if not any(
        [args.parser, args.schema, args.emulator, args.save_sample, args.all]
    ):
        args.all = True

    results = []

    if args.all or args.parser:
        results.append(("Parser", test_parser()))

    if args.all or args.schema:
        results.append(("Schema", test_json_schema()))

    if args.save_sample:
        save_sample_json(Path(args.save_sample))

    if args.emulator:
        run_zmq_emulator(args.port, args.duration)
        return  # Emulator runs indefinitely

    # Print summary
    if results:
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        all_pass = True
        for name, passed in results:
            status = "PASS" if passed else "FAIL"
            print(f"  {name}: {status}")
            if not passed:
                all_pass = False

        if all_pass:
            print("\nAll tests passed!")
            sys.exit(0)
        else:
            print("\nSome tests failed!")
            sys.exit(1)


if __name__ == "__main__":
    main()
