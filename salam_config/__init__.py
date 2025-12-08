"""
gem5-SALAM Unified Configuration System

This package provides a unified configuration and generation system for gem5-SALAM,
replacing the previous disconnected components with a clean, maintainable architecture.

Main components:
- cli: Command-line interface for configuration generation
- core: Core configuration management and validation
- generators: Code generators for Python configs, C headers, and C++ classes
- models: Data models for functional units, instructions, and accelerators
- data: Power model database and schemas
"""

__version__ = "2.0.0"
__author__ = "gem5-SALAM Team"

from .core.logging_config import SALAMLogger

# Initialize logging on import
_logger = SALAMLogger()

def get_logger(name: str):
    """Get a logger for the specified module."""
    return _logger.get_logger(name)
