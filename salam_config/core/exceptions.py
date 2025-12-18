"""
Custom exceptions for gem5-SALAM configuration system.

Provides structured exception handling with context information
for better debugging and error reporting.
"""


__version__ = "3.0.0.pre[1.0.0]"

from typing import Optional, List, Dict, Any


class SALAMConfigError(Exception):
    """Base exception for all SALAM configuration errors."""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self):
        if self.context:
            ctx_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} [{ctx_str}]"
        return self.message


class ValidationError(SALAMConfigError):
    """Raised when YAML configuration validation fails."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        line_number: Optional[int] = None,
        errors: Optional[List[str]] = None,
    ):
        context = {}
        if file_path:
            context["file"] = file_path
        if line_number:
            context["line"] = line_number

        super().__init__(message, context)
        self.file_path = file_path
        self.line_number = line_number
        self.errors = errors or []

    def format_errors(self) -> str:
        """Format all validation errors for display."""
        lines = [f"Validation Error: {self.message}"]
        if self.file_path:
            lines.append(f"  File: {self.file_path}")
        if self.line_number:
            lines.append(f"  Line: {self.line_number}")
        if self.errors:
            lines.append("  Errors:")
            for error in self.errors:
                lines.append(f"    - {error}")
        return "\n".join(lines)


class GenerationError(SALAMConfigError):
    """Raised when code generation fails."""

    def __init__(
        self,
        message: str,
        generator: Optional[str] = None,
        output_path: Optional[str] = None,
    ):
        context = {}
        if generator:
            context["generator"] = generator
        if output_path:
            context["output"] = output_path

        super().__init__(message, context)
        self.generator = generator
        self.output_path = output_path


class PowerModelError(SALAMConfigError):
    """Raised when power model lookup or calculation fails."""

    def __init__(
        self,
        message: str,
        functional_unit: Optional[str] = None,
        cycle_time: Optional[str] = None,
    ):
        context = {}
        if functional_unit:
            context["fu"] = functional_unit
        if cycle_time:
            context["cycle_time"] = cycle_time

        super().__init__(message, context)
        self.functional_unit = functional_unit
        self.cycle_time = cycle_time


class ConfigFileNotFoundError(SALAMConfigError):
    """Raised when a required configuration file is not found."""

    def __init__(self, file_path: str, expected_type: str = "configuration"):
        super().__init__(
            f"{expected_type.capitalize()} file not found: {file_path}",
            {"path": file_path, "type": expected_type},
        )
        self.file_path = file_path
        self.expected_type = expected_type


class InvalidCycleTimeError(SALAMConfigError):
    """Raised when an unsupported cycle time is specified."""

    SUPPORTED_CYCLE_TIMES = ["1ns", "2ns", "3ns", "4ns", "5ns", "6ns", "10ns"]

    def __init__(self, cycle_time: str):
        super().__init__(
            f"Unsupported cycle time: {cycle_time}. "
            f"Supported values: {', '.join(self.SUPPORTED_CYCLE_TIMES)}",
            {"cycle_time": cycle_time},
        )
        self.cycle_time = cycle_time


class AcceleratorConfigError(SALAMConfigError):
    """Raised when accelerator configuration is invalid."""

    def __init__(
        self,
        message: str,
        accelerator_name: Optional[str] = None,
        field: Optional[str] = None,
    ):
        context = {}
        if accelerator_name:
            context["accelerator"] = accelerator_name
        if field:
            context["field"] = field

        super().__init__(message, context)
        self.accelerator_name = accelerator_name
        self.field = field


class DMAConfigError(SALAMConfigError):
    """Raised when DMA configuration is invalid."""

    def __init__(
        self,
        message: str,
        dma_name: Optional[str] = None,
        dma_type: Optional[str] = None,
    ):
        context = {}
        if dma_name:
            context["dma"] = dma_name
        if dma_type:
            context["type"] = dma_type

        super().__init__(message, context)
        self.dma_name = dma_name
        self.dma_type = dma_type


class AddressAllocationError(SALAMConfigError):
    """Raised when memory address allocation fails."""

    def __init__(
        self,
        message: str,
        requested_size: Optional[int] = None,
        current_address: Optional[int] = None,
        max_address: Optional[int] = None,
    ):
        context = {}
        if requested_size:
            context["size"] = hex(requested_size)
        if current_address:
            context["current"] = hex(current_address)
        if max_address:
            context["max"] = hex(max_address)

        super().__init__(message, context)
        self.requested_size = requested_size
        self.current_address = current_address
        self.max_address = max_address
