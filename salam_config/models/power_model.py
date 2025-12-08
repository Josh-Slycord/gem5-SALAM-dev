"""
Power Model Database Loader

Loads and provides access to the centralized power model data for all functional units.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from ..core.logging_config import get_logger
from ..core.exceptions import PowerModelError, InvalidCycleTimeError

logger = get_logger("power_model")


@dataclass
class TimingData:
    """Power and timing data for a specific cycle time."""
    int_power: float      # Internal power (mW)
    switch_power: float   # Switching power (mW)
    dyn_power: float      # Dynamic power (mW)
    dyn_energy: float     # Dynamic energy (pJ)
    leak_power: float     # Leakage power (mW)
    area: float           # Area (um^2)
    critical_path: Optional[float] = None  # Critical path delay (ns)

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> 'TimingData':
        """Create TimingData from dictionary."""
        return cls(
            int_power=data.get('int_power', 0.0),
            switch_power=data.get('switch_power', 0.0),
            dyn_power=data.get('dyn_power', 0.0),
            dyn_energy=data.get('dyn_energy', 0.0),
            leak_power=data.get('leak_power', 0.0),
            area=data.get('area', 0.0),
            critical_path=data.get('critical_path')
        )


@dataclass
class FunctionalUnitModel:
    """Model for a functional unit with all timing data."""
    name: str
    enum_value: int
    description: str
    default_cycles: int
    instructions: List[str]
    timing: Dict[str, TimingData]
    per_bit: bool = False

    def get_timing(self, cycle_time: str) -> TimingData:
        """Get timing data for a specific cycle time."""
        if cycle_time not in self.timing:
            # Fall back to 5ns if available
            if '5ns' in self.timing:
                logger.warning(
                    f"Cycle time {cycle_time} not available for {self.name}, "
                    f"using 5ns fallback"
                )
                return self.timing['5ns']
            raise PowerModelError(
                f"No timing data available for cycle time {cycle_time}",
                functional_unit=self.name,
                cycle_time=cycle_time
            )
        return self.timing[cycle_time]


class PowerModelDatabase:
    """
    Central database for power model data.

    Loads power model from YAML file and provides lookup methods
    for functional unit power/area/timing characteristics.
    """

    SUPPORTED_CYCLE_TIMES = ['1ns', '2ns', '3ns', '4ns', '5ns', '6ns', '10ns']

    def __init__(self, data_path: Optional[Path] = None):
        """
        Initialize power model database.

        Args:
            data_path: Path to power model YAML file.
                      If None, uses default location.
        """
        if data_path is None:
            # Default to package data directory
            data_path = Path(__file__).parent.parent / 'data' / 'power_model_40nm.yaml'

        self.data_path = data_path
        self._data: Dict[str, Any] = {}
        self._functional_units: Dict[str, FunctionalUnitModel] = {}
        self._instruction_mapping: Dict[str, str] = {}
        self._loaded = False

        self._load()

    def _load(self):
        """Load power model data from YAML file."""
        if not self.data_path.exists():
            raise PowerModelError(
                f"Power model file not found: {self.data_path}"
            )

        logger.info(f"Loading power model from {self.data_path}")

        try:
            with open(self.data_path, 'r') as f:
                self._data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise PowerModelError(f"Failed to parse power model YAML: {e}")

        # Parse functional units
        for name, fu_data in self._data.get('functional_units', {}).items():
            timing = {}
            for cycle_time, timing_data in fu_data.get('timing', {}).items():
                timing[cycle_time] = TimingData.from_dict(timing_data)

            self._functional_units[name] = FunctionalUnitModel(
                name=name,
                enum_value=fu_data.get('enum_value', 0),
                description=fu_data.get('description', ''),
                default_cycles=fu_data.get('default_cycles', 1),
                instructions=fu_data.get('instructions', []),
                timing=timing,
                per_bit=fu_data.get('per_bit', False)
            )

        # Parse instruction mapping
        self._instruction_mapping = self._data.get('instruction_mapping', {})

        self._loaded = True
        logger.info(
            f"Loaded power model: {len(self._functional_units)} functional units, "
            f"{len(self._instruction_mapping)} instruction mappings"
        )

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get power model metadata."""
        return self._data.get('metadata', {})

    @property
    def technology_node(self) -> str:
        """Get technology node."""
        return self.metadata.get('technology_node', '40nm')

    @property
    def default_latencies(self) -> Dict[str, int]:
        """Get default latencies for operation types."""
        return self._data.get('default_latencies', {})

    def get_functional_unit(self, name: str) -> FunctionalUnitModel:
        """
        Get functional unit model by name.

        Args:
            name: Functional unit name (e.g., 'integer_adder', 'float_multiplier')

        Returns:
            FunctionalUnitModel instance

        Raises:
            PowerModelError: If functional unit not found
        """
        if name not in self._functional_units:
            raise PowerModelError(
                f"Unknown functional unit: {name}",
                functional_unit=name
            )
        return self._functional_units[name]

    def get_functional_unit_for_instruction(self, instruction: str) -> str:
        """
        Get the functional unit name for an instruction.

        Args:
            instruction: LLVM IR instruction name (e.g., 'fadd', 'mul')

        Returns:
            Functional unit name

        Raises:
            PowerModelError: If instruction not mapped
        """
        if instruction not in self._instruction_mapping:
            logger.warning(f"No mapping for instruction: {instruction}")
            return 'bit_register'  # Default to register
        return self._instruction_mapping[instruction]

    def get_timing(
        self,
        functional_unit: str,
        cycle_time: str
    ) -> TimingData:
        """
        Get timing data for a functional unit at a specific cycle time.

        Args:
            functional_unit: Functional unit name
            cycle_time: Cycle time (e.g., '5ns')

        Returns:
            TimingData instance
        """
        self._validate_cycle_time(cycle_time)
        fu = self.get_functional_unit(functional_unit)
        return fu.get_timing(cycle_time)

    def get_power(
        self,
        functional_unit: str,
        cycle_time: str
    ) -> Dict[str, float]:
        """
        Get power data for a functional unit.

        Args:
            functional_unit: Functional unit name
            cycle_time: Cycle time

        Returns:
            Dictionary with power values
        """
        timing = self.get_timing(functional_unit, cycle_time)
        return {
            'internal_power': timing.int_power,
            'switch_power': timing.switch_power,
            'dynamic_power': timing.dyn_power,
            'leakage_power': timing.leak_power
        }

    def get_area(self, functional_unit: str, cycle_time: str) -> float:
        """Get area for a functional unit."""
        timing = self.get_timing(functional_unit, cycle_time)
        return timing.area

    def get_energy(self, functional_unit: str, cycle_time: str) -> float:
        """Get dynamic energy for a functional unit."""
        timing = self.get_timing(functional_unit, cycle_time)
        return timing.dyn_energy

    def list_functional_units(self) -> List[str]:
        """Get list of all functional unit names."""
        return list(self._functional_units.keys())

    def list_instructions(self) -> List[str]:
        """Get list of all mapped instructions."""
        return list(self._instruction_mapping.keys())

    def _validate_cycle_time(self, cycle_time: str):
        """Validate that cycle time is supported."""
        if cycle_time not in self.SUPPORTED_CYCLE_TIMES:
            raise InvalidCycleTimeError(cycle_time)

    def to_yaml_config(
        self,
        functional_unit: str,
        cycle_time: str
    ) -> Dict[str, Any]:
        """
        Generate YAML-compatible configuration for a functional unit.

        This can be used to generate benchmark-specific FU configurations.

        Args:
            functional_unit: Functional unit name
            cycle_time: Cycle time

        Returns:
            Dictionary ready for YAML serialization
        """
        fu = self.get_functional_unit(functional_unit)
        timing = fu.get_timing(cycle_time)

        return {
            'functional_unit': {
                'parameters': {
                    'alias': fu.name,
                    'stages': 3 if 'float' in fu.name or 'double' in fu.name else 1,
                    'cycles': fu.default_cycles,
                    'enum_value': fu.enum_value,
                    'limit': 0
                },
                'power_model': {
                    'units': {
                        'power': 'mW',
                        'energy': 'pJ',
                        'time': 'ns',
                        'area': 'um^2'
                    },
                    'latency': int(cycle_time.replace('ns', '')),
                    'internal_power': timing.int_power,
                    'switch_power': timing.switch_power,
                    'dynamic_power': timing.dyn_power,
                    'dynamic_energy': timing.dyn_energy,
                    'leakage_power': timing.leak_power,
                    'area': timing.area,
                    'path_delay': timing.critical_path or 0.0
                }
            }
        }


# Module-level singleton
_power_model: Optional[PowerModelDatabase] = None


def get_power_model() -> PowerModelDatabase:
    """Get the global power model database instance."""
    global _power_model
    if _power_model is None:
        _power_model = PowerModelDatabase()
    return _power_model
