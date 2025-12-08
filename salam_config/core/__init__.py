"""
Core configuration management modules.

- config_manager: Central orchestrator for all configuration generation
- logging_config: Unified logging infrastructure
- schema_validator: YAML schema validation
- exceptions: Custom exception classes
"""

from .logging_config import SALAMLogger, get_logger
from .exceptions import (
    SALAMConfigError,
    ValidationError,
    GenerationError,
    PowerModelError,
    ConfigFileNotFoundError,
    InvalidCycleTimeError,
    AcceleratorConfigError,
    DMAConfigError,
    AddressAllocationError
)
from .config_manager import ConfigManager, GenerationResult, create_manager
from .schema_validator import (
    SchemaValidator,
    ValidationResult,
    validate_config,
    validate_config_file
)

__all__ = [
    # Logging
    'SALAMLogger',
    'get_logger',
    # Config Manager
    'ConfigManager',
    'GenerationResult',
    'create_manager',
    # Schema Validator
    'SchemaValidator',
    'ValidationResult',
    'validate_config',
    'validate_config_file',
    # Exceptions
    'SALAMConfigError',
    'ValidationError',
    'GenerationError',
    'PowerModelError',
    'ConfigFileNotFoundError',
    'InvalidCycleTimeError',
    'AcceleratorConfigError',
    'DMAConfigError',
    'AddressAllocationError',
]
