# ==============================================================================
# config_loader.py - Accelerator Configuration Loader
# ==============================================================================
"""YAML Configuration File Loader for gem5-SALAM GUI.

This module provides utilities for loading and extracting data from
gem5-SALAM accelerator configuration files (config.yml). These files
define the hardware parameters for accelerator simulations.

Configuration Structure::

    acc_cluster:
        functional_units:
            int_alu:
                count: 4
                cycles: 1
            fp_mul:
                count: 2
                cycles: 3
            ...
        spm_size: 65536
        cache_size: 32768
        dma:
            read_bandwidth: 16
            write_bandwidth: 16

Functions:
    - load_config(): Load YAML file into dictionary
    - get_accelerator_config(): Extract acc_cluster section
    - get_functional_units(): Extract FU type/count mapping
    - get_memory_config(): Extract memory configuration

Example:
    Loading and inspecting configuration::

        from salam_gui.data.config_loader import (
            load_config, get_functional_units, get_memory_config
        )
        from pathlib import Path

        # Load configuration
        config = load_config(Path("configs/SALAM/fft_config.yml"))

        # Get FU counts
        fus = get_functional_units(config)
        # {'int_alu': 4, 'fp_mul': 2, 'memory': 1}

        # Get memory configuration
        mem = get_memory_config(config)
        # {'spm_size': 65536, 'cache_size': 32768, 'dma_config': {...}}

Configuration File Locations:
    - configs/SALAM/generated/: Auto-generated benchmark configs
    - benchmarks/*/config.yml: Benchmark-specific configs
    - Custom paths specified by user

See Also:
    - HWAccConfig: Python class representation of config
    - simulation_panel: UI for selecting configuration
    - acc_cluster.hh: C++ accelerator cluster implementation
"""


__version__ = "3.0.0.pre[1.0.0]"

from pathlib import Path
from typing import Dict, Any, Optional
import yaml


def load_config(file_path: Path) -> Dict[str, Any]:
    """
    Load a YAML configuration file.

    Args:
        file_path: Path to config.yml

    Returns:
        Dictionary containing configuration
    """
    with open(file_path, 'r') as f:
        return yaml.safe_load(f) or {}


def get_accelerator_config(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract accelerator configuration from loaded config.

    Args:
        config: Full configuration dictionary

    Returns:
        Accelerator cluster configuration or None
    """
    return config.get('acc_cluster')


def get_functional_units(config: Dict[str, Any]) -> Dict[str, int]:
    """
    Extract functional unit counts from configuration.

    Args:
        config: Full configuration dictionary

    Returns:
        Dictionary mapping FU type to count
    """
    acc = get_accelerator_config(config)
    if not acc:
        return {}

    fu_config = acc.get('functional_units', {})
    return {
        name: fu.get('count', 1)
        for name, fu in fu_config.items()
        if isinstance(fu, dict)
    }


def get_memory_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract memory configuration.

    Args:
        config: Full configuration dictionary

    Returns:
        Memory configuration dictionary
    """
    acc = get_accelerator_config(config)
    if not acc:
        return {}

    return {
        'spm_size': acc.get('spm_size', 0),
        'cache_size': acc.get('cache_size', 0),
        'dma_config': acc.get('dma', {}),
    }
