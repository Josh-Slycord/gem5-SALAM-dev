"""
Configuration Manager for gem5-SALAM

Central orchestrator for configuration generation and management.
Coordinates validation, power model loading, and all generation tasks.
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from .logging_config import get_logger
from .exceptions import (
    SALAMConfigError,
    ValidationError,
    ConfigFileNotFoundError,
    InvalidCycleTimeError
)
from ..models.power_model import get_power_model, PowerModelDatabase

logger = get_logger("config_manager")


@dataclass
class GenerationResult:
    """Result of a generation operation."""
    success: bool
    generated_files: List[str] = field(default_factory=list)
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


@dataclass
class AcceleratorConfig:
    """Parsed accelerator configuration."""
    name: str
    ir_path: str
    pio_size: int = 32
    variables: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DMAConfig:
    """Parsed DMA configuration."""
    name: str
    dma_type: str = "NonCoherent"
    max_req_size: int = 128
    buffer_size: int = 256


@dataclass
class ClusterConfig:
    """Parsed accelerator cluster configuration."""
    name: str
    dmas: List[DMAConfig] = field(default_factory=list)
    accelerators: List[AcceleratorConfig] = field(default_factory=list)


class ConfigManager:
    """
    Central configuration manager for gem5-SALAM.

    Handles:
    - Loading and validating YAML configurations
    - Loading power model database
    - Coordinating generation of Python configs, C headers, and C++ classes
    """

    SUPPORTED_CYCLE_TIMES = ['1ns', '2ns', '3ns', '4ns', '5ns', '6ns', '10ns']
    DEFAULT_BASE_ADDRESS = 0x10020000
    DEFAULT_ALIGNMENT = 64

    def __init__(self, verbose: bool = False):
        """
        Initialize configuration manager.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose
        self._power_model: Optional[PowerModelDatabase] = None
        self._m5_path = os.environ.get('M5_PATH', '')

        if verbose:
            from .logging_config import SALAMLogger
            SALAMLogger().set_console_level('DEBUG')

        logger.info("ConfigManager initialized")

    @property
    def power_model(self) -> PowerModelDatabase:
        """Get power model database (lazy loaded)."""
        if self._power_model is None:
            self._power_model = get_power_model()
        return self._power_model

    def load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load and parse a YAML configuration file.

        Args:
            config_path: Path to configuration YAML file

        Returns:
            Parsed configuration dictionary

        Raises:
            ConfigFileNotFoundError: If file doesn't exist
            ValidationError: If YAML is invalid
        """
        path = Path(config_path)
        if not path.exists():
            raise ConfigFileNotFoundError(str(path))

        logger.info(f"Loading configuration from {config_path}")

        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)

            if config is None:
                raise ValidationError("Empty configuration file", file_path=str(path))

            logger.debug(f"Loaded configuration with keys: {list(config.keys())}")
            return config

        except yaml.YAMLError as e:
            raise ValidationError(
                f"YAML parsing error: {e}",
                file_path=str(path)
            )

    def parse_cluster_config(self, config: Dict[str, Any]) -> ClusterConfig:
        """
        Parse acc_cluster section of configuration.

        Args:
            config: Full configuration dictionary

        Returns:
            ClusterConfig object
        """
        if 'acc_cluster' not in config:
            raise ValidationError("Configuration missing 'acc_cluster' section")

        acc_cluster = config['acc_cluster']
        if not isinstance(acc_cluster, list):
            raise ValidationError("'acc_cluster' must be a list")

        cluster_name = "unnamed_cluster"
        dmas = []
        accelerators = []

        for item in acc_cluster:
            if isinstance(item, dict):
                if 'Name' in item:
                    cluster_name = item['Name']
                elif 'DMA' in item:
                    for dma_item in item['DMA']:
                        dmas.append(DMAConfig(
                            name=dma_item.get('Name', 'unnamed_dma'),
                            dma_type=dma_item.get('Type', 'NonCoherent'),
                            max_req_size=dma_item.get('MaxReqSize', 128),
                            buffer_size=dma_item.get('BufferSize', 256)
                        ))
                elif 'Accelerator' in item:
                    for acc_item in item['Accelerator']:
                        if isinstance(acc_item, dict) and 'Name' in acc_item:
                            variables = []
                            for sub_item in item['Accelerator']:
                                if isinstance(sub_item, dict) and 'Var' in sub_item:
                                    variables.extend(sub_item['Var'])

                            accelerators.append(AcceleratorConfig(
                                name=acc_item.get('Name', 'unnamed_acc'),
                                ir_path=acc_item.get('IrPath', ''),
                                pio_size=acc_item.get('PIOSize', 32),
                                variables=variables
                            ))

        logger.debug(f"Parsed cluster: {cluster_name} with {len(dmas)} DMAs, {len(accelerators)} accelerators")
        return ClusterConfig(name=cluster_name, dmas=dmas, accelerators=accelerators)

    def validate_cycle_time(self, cycle_time: str) -> None:
        """
        Validate that cycle time is supported.

        Args:
            cycle_time: Cycle time string (e.g., '5ns')

        Raises:
            InvalidCycleTimeError: If cycle time not supported
        """
        if cycle_time not in self.SUPPORTED_CYCLE_TIMES:
            raise InvalidCycleTimeError(cycle_time)

    def generate_all(
        self,
        benchmark: str,
        bench_dir: str = "benchmarks/sys_validation",
        cycle_time: str = "5ns",
        base_address: int = DEFAULT_BASE_ADDRESS,
        dry_run: bool = False
    ) -> GenerationResult:
        """
        Generate all configuration files for a benchmark.

        This includes:
        - Python configuration files for gem5
        - C header files with hardware defines
        - C++ functional unit class files

        Args:
            benchmark: Benchmark name
            bench_dir: Benchmark directory relative to M5_PATH
            cycle_time: Cycle time (default: 5ns)
            base_address: Base memory address (default: 0x10020000)
            dry_run: If True, show what would be generated without creating files

        Returns:
            GenerationResult with status and list of generated files
        """
        logger.info(f"Generating configurations for benchmark: {benchmark}")
        logger.info(f"  Directory: {bench_dir}")
        logger.info(f"  Cycle time: {cycle_time}")
        logger.info(f"  Base address: {hex(base_address)}")

        # Validate inputs
        try:
            self.validate_cycle_time(cycle_time)
        except InvalidCycleTimeError as e:
            return GenerationResult(success=False, error=str(e))

        # Build paths
        if not self._m5_path:
            return GenerationResult(
                success=False,
                error="M5_PATH environment variable not set"
            )

        bench_path = Path(self._m5_path) / bench_dir / benchmark
        if not bench_path.exists():
            return GenerationResult(
                success=False,
                error=f"Benchmark directory not found: {bench_path}"
            )

        config_file = bench_path / "config.yml"
        if not config_file.exists():
            # Try alternate names
            for alt_name in ["config.yaml", f"{benchmark}_config.yml"]:
                alt_file = bench_path / alt_name
                if alt_file.exists():
                    config_file = alt_file
                    break
            else:
                return GenerationResult(
                    success=False,
                    error=f"Configuration file not found in {bench_path}"
                )

        # Load and parse configuration
        try:
            config = self.load_config(str(config_file))
            cluster = self.parse_cluster_config(config)
        except SALAMConfigError as e:
            return GenerationResult(success=False, error=str(e))

        generated_files = []
        warnings = []

        if dry_run:
            logger.info("DRY RUN - No files will be generated")

        # Generate Python config
        try:
            py_files = self._generate_python_config(
                benchmark, bench_path, cluster, config, dry_run
            )
            generated_files.extend(py_files)
        except Exception as e:
            warnings.append(f"Python config generation failed: {e}")
            logger.warning(f"Python config generation failed: {e}")

        # Generate C headers
        try:
            h_files = self._generate_c_headers(
                benchmark, bench_path, cluster, config, base_address, dry_run
            )
            generated_files.extend(h_files)
        except Exception as e:
            warnings.append(f"C header generation failed: {e}")
            logger.warning(f"C header generation failed: {e}")

        # Generate HW profile data
        try:
            hw_files = self._generate_hw_profile(
                benchmark, bench_path, cycle_time, dry_run
            )
            generated_files.extend(hw_files)
        except Exception as e:
            warnings.append(f"HW profile generation failed: {e}")
            logger.warning(f"HW profile generation failed: {e}")

        return GenerationResult(
            success=True,
            generated_files=generated_files,
            warnings=warnings
        )

    def _generate_python_config(
        self,
        benchmark: str,
        bench_path: Path,
        cluster: ClusterConfig,
        config: Dict[str, Any],
        dry_run: bool
    ) -> List[str]:
        """Generate Python configuration files for gem5."""
        logger.info("Generating Python configuration...")

        output_dir = Path(self._m5_path) / "configs" / "SALAM" / "generated"
        output_file = output_dir / f"{benchmark}_config.py"

        if dry_run:
            logger.info(f"Would generate: {output_file}")
            return [str(output_file)]

        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate Python content
        content = self._render_python_config(benchmark, cluster, config)

        with open(output_file, 'w') as f:
            f.write(content)

        logger.info(f"Generated: {output_file}")
        return [str(output_file)]

    def _render_python_config(
        self,
        benchmark: str,
        cluster: ClusterConfig,
        config: Dict[str, Any]
    ) -> str:
        """Render Python configuration file content."""
        lines = [
            '"""',
            f'Auto-generated configuration for {benchmark}',
            f'Cluster: {cluster.name}',
            '"""',
            '',
            'from m5.objects import *',
            'from m5.util import *',
            '',
            f'# Configuration for {benchmark}',
            f'CLUSTER_NAME = "{cluster.name}"',
            '',
            '# DMA Configurations',
            'DMA_CONFIGS = [',
        ]

        for dma in cluster.dmas:
            lines.append(f'    {{"name": "{dma.name}", "type": "{dma.dma_type}", '
                        f'"max_req_size": {dma.max_req_size}, "buffer_size": {dma.buffer_size}}},')

        lines.append(']')
        lines.append('')
        lines.append('# Accelerator Configurations')
        lines.append('ACCELERATOR_CONFIGS = [')

        for acc in cluster.accelerators:
            lines.append(f'    {{"name": "{acc.name}", "ir_path": "{acc.ir_path}", '
                        f'"pio_size": {acc.pio_size}}},')

        lines.append(']')
        lines.append('')

        return '\n'.join(lines)

    def _generate_c_headers(
        self,
        benchmark: str,
        bench_path: Path,
        cluster: ClusterConfig,
        config: Dict[str, Any],
        base_address: int,
        dry_run: bool
    ) -> List[str]:
        """Generate C header files with hardware defines."""
        logger.info("Generating C headers...")

        output_file = bench_path / "hw" / f"{benchmark}_hw_defines.h"

        if dry_run:
            logger.info(f"Would generate: {output_file}")
            return [str(output_file)]

        output_file.parent.mkdir(parents=True, exist_ok=True)

        content = self._render_c_header(benchmark, cluster, base_address)

        with open(output_file, 'w') as f:
            f.write(content)

        logger.info(f"Generated: {output_file}")
        return [str(output_file)]

    def _render_c_header(
        self,
        benchmark: str,
        cluster: ClusterConfig,
        base_address: int
    ) -> str:
        """Render C header file content."""
        guard = f"{benchmark.upper()}_HW_DEFINES_H"
        lines = [
            '/**',
            f' * Auto-generated hardware defines for {benchmark}',
            f' * Cluster: {cluster.name}',
            ' */',
            '',
            f'#ifndef {guard}',
            f'#define {guard}',
            '',
            '/* Memory Base Addresses */',
            f'#define BASE_ADDRESS 0x{base_address:08X}',
            '',
            '/* DMA Configurations */',
        ]

        for i, dma in enumerate(cluster.dmas):
            name_upper = dma.name.upper()
            lines.append(f'#define {name_upper}_MAX_REQ_SIZE {dma.max_req_size}')
            lines.append(f'#define {name_upper}_BUFFER_SIZE {dma.buffer_size}')

        lines.append('')
        lines.append('/* Accelerator Configurations */')

        for i, acc in enumerate(cluster.accelerators):
            name_upper = acc.name.upper()
            lines.append(f'#define {name_upper}_PIO_SIZE {acc.pio_size}')

        lines.append('')
        lines.append(f'#endif /* {guard} */')
        lines.append('')

        return '\n'.join(lines)

    def _generate_hw_profile(
        self,
        benchmark: str,
        bench_path: Path,
        cycle_time: str,
        dry_run: bool
    ) -> List[str]:
        """Generate HW profile data using power model."""
        logger.info("Generating HW profile data...")

        output_dir = Path(self._m5_path) / "src" / "hwacc" / "HWModeling" / "generated"
        generated_files = []

        if dry_run:
            for fu_name in self.power_model.list_functional_units():
                output_file = output_dir / f"{fu_name}_{benchmark}.yaml"
                logger.info(f"Would generate: {output_file}")
                generated_files.append(str(output_file))
            return generated_files

        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate YAML power data for each FU at the specified cycle time
        for fu_name in self.power_model.list_functional_units():
            try:
                fu_config = self.power_model.to_yaml_config(fu_name, cycle_time)

                output_file = output_dir / f"{fu_name}_{benchmark}.yaml"
                with open(output_file, 'w') as f:
                    yaml.dump(fu_config, f, default_flow_style=False)

                generated_files.append(str(output_file))
                logger.debug(f"Generated: {output_file}")

            except Exception as e:
                logger.warning(f"Failed to generate profile for {fu_name}: {e}")

        logger.info(f"Generated {len(generated_files)} HW profile files")
        return generated_files

    def get_benchmark_info(self, benchmark: str, bench_dir: str = "benchmarks/sys_validation") -> Dict[str, Any]:
        """
        Get information about a benchmark.

        Args:
            benchmark: Benchmark name
            bench_dir: Benchmark directory

        Returns:
            Dictionary with benchmark information
        """
        bench_path = Path(self._m5_path) / bench_dir / benchmark

        info = {
            'name': benchmark,
            'path': str(bench_path),
            'exists': bench_path.exists(),
            'has_config': False,
            'has_hw_dir': False,
            'ir_files': [],
        }

        if bench_path.exists():
            for config_name in ['config.yml', 'config.yaml', f'{benchmark}_config.yml']:
                if (bench_path / config_name).exists():
                    info['has_config'] = True
                    info['config_file'] = str(bench_path / config_name)
                    break

            hw_dir = bench_path / 'hw'
            if hw_dir.exists():
                info['has_hw_dir'] = True
                info['ir_files'] = [str(f) for f in hw_dir.glob('*.ll')]

        return info


def create_manager(verbose: bool = False) -> ConfigManager:
    """Factory function to create a ConfigManager instance."""
    return ConfigManager(verbose=verbose)
