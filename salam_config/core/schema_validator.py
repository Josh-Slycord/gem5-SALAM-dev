"""
Schema Validator for gem5-SALAM Configuration Files

Validates YAML configuration files against the expected schema.
Provides detailed error messages with line numbers where possible.
"""


__version__ = "3.0.0.pre[1.0.0]"

import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

from .logging_config import get_logger
from .exceptions import ValidationError

logger = get_logger("schema_validator")


@dataclass
class ValidationResult:
    """Result of a validation operation."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: Dict[str, Any] = field(default_factory=dict)


class SchemaValidator:
    """
    Validates gem5-SALAM configuration files.

    Checks for:
    - Required sections (acc_cluster)
    - Valid DMA configurations
    - Valid Accelerator configurations
    - Valid Variable definitions
    - Valid hw_config instructions
    """

    # Required fields for different config types
    DMA_REQUIRED_FIELDS = {"Name"}
    DMA_OPTIONAL_FIELDS = {
        "Type",
        "MaxReqSize",
        "BufferSize",
        "WrReqSize",
        "RdReqSize",
        "Flags",
        "Debug",
    }

    ACCELERATOR_REQUIRED_FIELDS = {"Name"}
    ACCELERATOR_OPTIONAL_FIELDS = {"IrPath", "PIOSize", "TopFunc"}

    VAR_REQUIRED_FIELDS = {"Name", "Type", "Size"}
    VAR_OPTIONAL_FIELDS = {"Access", "Port"}

    VALID_DMA_TYPES = {"NonCoherent", "Stream", "Coherent"}
    VALID_VAR_TYPES = {"SPM", "Cache", "Stream", "Register"}
    VALID_INSTRUCTIONS = {
        "add",
        "sub",
        "mul",
        "sdiv",
        "udiv",
        "srem",
        "urem",
        "fadd",
        "fsub",
        "fmul",
        "fdiv",
        "frem",
        "and",
        "or",
        "xor",
        "shl",
        "ashr",
        "lshr",
        "icmp",
        "fcmp",
        "load",
        "store",
        "gep",
        "alloca",
        "fence",
        "sext",
        "zext",
        "trunc",
        "fpext",
        "fptrunc",
        "fptosi",
        "fptoui",
        "sitofp",
        "uitofp",
        "inttoptr",
        "ptrtoint",
        "bitcast",
        "addrspacecast",
        "br",
        "indirectbr",
        "switch",
        "call",
        "invoke",
        "ret",
        "resume",
        "unreachable",
        "phi",
        "select",
        "vaarg",
        "landingpad",
    }

    def __init__(self):
        """Initialize schema validator."""
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(
        self, config: Dict[str, Any], config_path: Optional[str] = None
    ) -> ValidationResult:
        """
        Validate a configuration dictionary.

        Args:
            config: Parsed YAML configuration
            config_path: Optional path for error messages

        Returns:
            ValidationResult with errors and warnings
        """
        self.errors = []
        self.warnings = []

        if config is None:
            self.errors.append("Configuration is empty or None")
            return self._build_result(config)

        # Check for acc_cluster section
        if "acc_cluster" not in config:
            self.errors.append("Missing required section: 'acc_cluster'")
        else:
            self._validate_acc_cluster(config["acc_cluster"])

        # Check for hw_config section (optional but validated if present)
        if "hw_config" in config:
            self._validate_hw_config(config["hw_config"])

        # Check for global section (optional)
        if "global" in config:
            self._validate_global_config(config["global"])

        return self._build_result(config)

    def _build_result(self, config: Dict[str, Any]) -> ValidationResult:
        """Build validation result."""
        info = {}
        if config:
            if "acc_cluster" in config:
                info["cluster_count"] = 1
                info["has_hw_config"] = "hw_config" in config
                info["has_global"] = "global" in config

        return ValidationResult(
            is_valid=len(self.errors) == 0,
            errors=self.errors.copy(),
            warnings=self.warnings.copy(),
            info=info,
        )

    def _validate_acc_cluster(self, acc_cluster: Any) -> None:
        """Validate acc_cluster section."""
        if not isinstance(acc_cluster, list):
            self.errors.append("'acc_cluster' must be a list")
            return

        has_name = False
        dma_count = 0
        acc_count = 0

        for i, item in enumerate(acc_cluster):
            if not isinstance(item, dict):
                self.errors.append(
                    f"acc_cluster[{i}]: Expected dict, got {type(item).__name__}"
                )
                continue

            if "Name" in item:
                has_name = True
                if not isinstance(item["Name"], str):
                    self.errors.append(f"acc_cluster[{i}].Name: Must be a string")

            if "DMA" in item:
                dma_count += len(item["DMA"]) if isinstance(item["DMA"], list) else 1
                self._validate_dma_list(item["DMA"], i)

            if "Accelerator" in item:
                acc_count += (
                    len(item["Accelerator"])
                    if isinstance(item["Accelerator"], list)
                    else 1
                )
                self._validate_accelerator_list(item["Accelerator"], i)

        if not has_name:
            self.warnings.append(
                "acc_cluster: Missing 'Name' field (cluster will be unnamed)"
            )

        if dma_count == 0:
            self.warnings.append("acc_cluster: No DMA configurations found")

        if acc_count == 0:
            self.warnings.append("acc_cluster: No Accelerator configurations found")

        logger.debug(
            f"Validated acc_cluster: {dma_count} DMAs, {acc_count} accelerators"
        )

    def _validate_dma_list(self, dma_list: Any, parent_idx: int) -> None:
        """Validate DMA configuration list."""
        if not isinstance(dma_list, list):
            self.errors.append(f"acc_cluster[{parent_idx}].DMA: Must be a list")
            return

        names_seen: Set[str] = set()

        for i, dma in enumerate(dma_list):
            prefix = f"acc_cluster[{parent_idx}].DMA[{i}]"

            if not isinstance(dma, dict):
                self.errors.append(f"{prefix}: Expected dict, got {type(dma).__name__}")
                continue

            # Check required fields
            for field in self.DMA_REQUIRED_FIELDS:
                if field not in dma:
                    self.errors.append(f"{prefix}: Missing required field '{field}'")

            # Check for duplicate names
            if "Name" in dma:
                name = dma["Name"]
                if name in names_seen:
                    self.errors.append(f"{prefix}: Duplicate DMA name '{name}'")
                names_seen.add(name)

            # Validate DMA type
            if "Type" in dma and dma["Type"] not in self.VALID_DMA_TYPES:
                self.warnings.append(
                    f"{prefix}: Unknown DMA type '{dma['Type']}'. "
                    f"Valid types: {', '.join(self.VALID_DMA_TYPES)}"
                )

            # Check for unknown fields
            known_fields = self.DMA_REQUIRED_FIELDS | self.DMA_OPTIONAL_FIELDS
            for field in dma.keys():
                if field not in known_fields:
                    self.warnings.append(f"{prefix}: Unknown field '{field}'")

    def _validate_accelerator_list(self, acc_list: Any, parent_idx: int) -> None:
        """Validate Accelerator configuration list."""
        if not isinstance(acc_list, list):
            self.errors.append(f"acc_cluster[{parent_idx}].Accelerator: Must be a list")
            return

        names_seen: Set[str] = set()
        has_vars = False

        for i, item in enumerate(acc_list):
            prefix = f"acc_cluster[{parent_idx}].Accelerator[{i}]"

            if not isinstance(item, dict):
                self.errors.append(
                    f"{prefix}: Expected dict, got {type(item).__name__}"
                )
                continue

            # Handle Var sections
            if "Var" in item:
                has_vars = True
                self._validate_var_list(item["Var"], parent_idx, i)
                continue

            # Check required fields for accelerator entry
            if "Name" in item:
                for field in self.ACCELERATOR_REQUIRED_FIELDS:
                    if field not in item:
                        self.errors.append(
                            f"{prefix}: Missing required field '{field}'"
                        )

                name = item["Name"]
                if name in names_seen:
                    self.errors.append(f"{prefix}: Duplicate accelerator name '{name}'")
                names_seen.add(name)

                # Check for unknown fields
                known_fields = (
                    self.ACCELERATOR_REQUIRED_FIELDS | self.ACCELERATOR_OPTIONAL_FIELDS
                )
                for field in item.keys():
                    if field not in known_fields:
                        self.warnings.append(f"{prefix}: Unknown field '{field}'")

    def _validate_var_list(self, var_list: Any, cluster_idx: int, acc_idx: int) -> None:
        """Validate Variable configuration list."""
        if not isinstance(var_list, list):
            self.errors.append(
                f"acc_cluster[{cluster_idx}].Accelerator[{acc_idx}].Var: Must be a list"
            )
            return

        names_seen: Set[str] = set()

        for i, var in enumerate(var_list):
            prefix = f"acc_cluster[{cluster_idx}].Accelerator[{acc_idx}].Var[{i}]"

            if not isinstance(var, dict):
                self.errors.append(f"{prefix}: Expected dict, got {type(var).__name__}")
                continue

            # Check required fields
            for field in self.VAR_REQUIRED_FIELDS:
                if field not in var:
                    self.errors.append(f"{prefix}: Missing required field '{field}'")

            # Check for duplicate names
            if "Name" in var:
                name = var["Name"]
                if name in names_seen:
                    self.errors.append(f"{prefix}: Duplicate variable name '{name}'")
                names_seen.add(name)

            # Validate variable type
            if "Type" in var and var["Type"] not in self.VALID_VAR_TYPES:
                self.warnings.append(
                    f"{prefix}: Unknown variable type '{var['Type']}'. "
                    f"Valid types: {', '.join(self.VALID_VAR_TYPES)}"
                )

            # Check size is numeric
            if "Size" in var and not isinstance(var["Size"], (int, float)):
                self.errors.append(f"{prefix}.Size: Must be a number")

    def _validate_hw_config(self, hw_config: Any) -> None:
        """Validate hw_config section."""
        if not isinstance(hw_config, dict):
            self.errors.append("'hw_config' must be a dictionary")
            return

        for bench_name, bench_config in hw_config.items():
            if not isinstance(bench_config, dict):
                self.warnings.append(f"hw_config.{bench_name}: Expected dict")
                continue

            if "instructions" in bench_config:
                self._validate_instructions(bench_config["instructions"], bench_name)

            if "functional_units" in bench_config:
                self._validate_functional_units(
                    bench_config["functional_units"], bench_name
                )

    def _validate_instructions(self, instructions: Any, bench_name: str) -> None:
        """Validate instruction configurations."""
        if not isinstance(instructions, dict):
            self.errors.append(
                f"hw_config.{bench_name}.instructions: Must be a dictionary"
            )
            return

        for inst_name, inst_config in instructions.items():
            prefix = f"hw_config.{bench_name}.instructions.{inst_name}"

            # Check if instruction is known
            if inst_name not in self.VALID_INSTRUCTIONS:
                self.warnings.append(f"{prefix}: Unknown instruction '{inst_name}'")

            if not isinstance(inst_config, dict):
                self.errors.append(f"{prefix}: Must be a dictionary")
                continue

            # Check for runtime_cycles
            if "runtime_cycles" in inst_config:
                cycles = inst_config["runtime_cycles"]
                if not isinstance(cycles, (int, float)) or cycles < 0:
                    self.errors.append(
                        f"{prefix}.runtime_cycles: Must be a non-negative number"
                    )

    def _validate_functional_units(self, fus: Any, bench_name: str) -> None:
        """Validate functional unit configurations."""
        if not isinstance(fus, dict):
            self.errors.append(
                f"hw_config.{bench_name}.functional_units: Must be a dictionary"
            )
            return

        for fu_name, fu_config in fus.items():
            prefix = f"hw_config.{bench_name}.functional_units.{fu_name}"

            if not isinstance(fu_config, dict):
                self.errors.append(f"{prefix}: Must be a dictionary")
                continue

            # Check cycles if present
            if "cycles" in fu_config:
                cycles = fu_config["cycles"]
                if not isinstance(cycles, (int, float)) or cycles < 0:
                    self.errors.append(
                        f"{prefix}.cycles: Must be a non-negative number"
                    )

    def _validate_global_config(self, global_config: Any) -> None:
        """Validate global configuration section."""
        if not isinstance(global_config, dict):
            self.errors.append("'global' must be a dictionary")
            return

        # Validate memory section
        if "memory" in global_config:
            mem = global_config["memory"]
            if isinstance(mem, dict):
                if "base_address" in mem:
                    addr = mem["base_address"]
                    if isinstance(addr, str):
                        try:
                            int(addr, 16) if addr.startswith("0x") else int(addr)
                        except ValueError:
                            self.errors.append(
                                f"global.memory.base_address: Invalid address '{addr}'"
                            )

        # Validate cache section
        if "cache" in global_config:
            cache = global_config["cache"]
            if isinstance(cache, dict):
                for field in ["l1_associativity", "l1_latency"]:
                    if field in cache and not isinstance(cache[field], int):
                        self.errors.append(f"global.cache.{field}: Must be an integer")


def validate_config_file(config_path: str) -> ValidationResult:
    """
    Validate a configuration file.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        ValidationResult with errors and warnings
    """
    path = Path(config_path)

    if not path.exists():
        return ValidationResult(
            is_valid=False, errors=[f"Configuration file not found: {config_path}"]
        )

    try:
        with open(path, "r") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return ValidationResult(is_valid=False, errors=[f"YAML parsing error: {e}"])

    validator = SchemaValidator()
    result = validator.validate(config, str(path))

    if result.is_valid:
        logger.info(f"Configuration is valid: {config_path}")
    else:
        logger.warning(f"Configuration has {len(result.errors)} errors: {config_path}")

    return result


def validate_config(config: Dict[str, Any]) -> ValidationResult:
    """
    Validate a configuration dictionary.

    Args:
        config: Parsed YAML configuration

    Returns:
        ValidationResult with errors and warnings
    """
    validator = SchemaValidator()
    return validator.validate(config)
