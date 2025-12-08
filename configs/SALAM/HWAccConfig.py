"""
gem5-SALAM Hardware Accelerator Configuration

Configures accelerator functional units and instructions with dynamic loading.
Replaces hardcoded instantiations with registry-based dynamic instantiation.
"""

import m5
from m5.objects import *
from m5.util import *
from configparser import ConfigParser
from pathlib import Path
import yaml
import os
import logging

# Set up logging
logger = logging.getLogger("salam.HWAccConfig")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# =============================================================================
# Functional Unit Registry
# Maps configuration names to gem5 SimObject classes
# =============================================================================
_FU_REGISTRY = {
    'bit_register': BitRegister,
    'bit_shifter': BitShifter,
    'bitwise_operations': BitwiseOperations,
    'integer_adder': IntegerAdder,
    'integer_multiplier': IntegerMultiplier,
    'float_adder': FloatAdder,
    'float_multiplier': FloatMultiplier,
    'float_divider': FloatDivider,
    'double_adder': DoubleAdder,
    'double_multiplier': DoubleMultiplier,
    'double_divider': DoubleDivider,
}

# =============================================================================
# Instruction Registry
# Maps LLVM IR instruction names to gem5 SimObject classes
# =============================================================================
_INST_REGISTRY = {
    # Arithmetic - Integer
    'add': Add,
    'sub': Sub,
    'mul': Mul,
    'sdiv': Sdiv,
    'udiv': Udiv,
    'srem': Srem,
    'urem': Urem,

    # Arithmetic - Floating Point
    'fadd': Fadd,
    'fsub': Fsub,
    'fmul': Fmul,
    'fdiv': Fdiv,
    'frem': Frem,

    # Bitwise Operations
    'and_inst': AndInst,
    'or_inst': OrInst,
    'xor_inst': XorInst,

    # Shift Operations
    'shl': Shl,
    'ashr': Ashr,
    'lshr': Lshr,

    # Comparison
    'icmp': Icmp,
    'fcmp': Fcmp,

    # Memory Operations
    'load': Load,
    'store': Store,
    'gep': Gep,
    'alloca': Alloca,
    'fence': Fence,

    # Type Conversions
    'sext': Sext,
    'zext': Zext,
    'trunc': Trunc,
    'fpext': Fpext,
    'fptrunc': Fptrunc,
    'fptosi': Fptosi,
    'fptoui': Fptoui,
    'uitofp': Uitofp,
    # Note: sitofp is implemented in C++ but has no separate SimObject class.
    # It uses cycle count from CycleCounts.py sitofp parameter (default: 1 cycle).
    'inttoptr': Inttoptr,
    'ptrtoint': Ptrtoint,
    'bitcast': Bitcast,
    'addrspacecast': Addrspacecast,

    # Control Flow
    'br': Br,
    'indirectbr': Indirectbr,
    'switch_inst': SwitchInst,
    'call': Call,
    'invoke': Invoke,
    'ret': Ret,
    'resume': Resume,
    'unreachable': Unreachable,

    # Other
    'phi': Phi,
    'select': Select,
    'vaarg': Vaarg,
    'landingpad': Landingpad,
}


def _load_hw_config(config_file, benchname, bench_path=None, m5_path_len=0):
    """
    Load hw_config from YAML configuration file.

    Args:
        config_file: Path to YAML configuration file
        benchname: Name of the benchmark
        bench_path: Path parts for mobilenetv2 special handling
        m5_path_len: Length of M5_PATH for mobilenetv2 handling

    Returns:
        Dictionary with instructions and their runtime_cycles, or None
    """
    try:
        with open(config_file, 'r') as f:
            # Check for mobilenetv2 multi-document format
            if bench_path and len(bench_path) > m5_path_len + 1:
                if bench_path[m5_path_len + 1] == 'mobilenetv2':
                    for yaml_inst_list in yaml.safe_load_all(f):
                        document = yaml_inst_list.get('acc_cluster', [{}])
                        if document:
                            current_acc = document[0].get('Name', '') + '_' + benchname
                            if len(bench_path) > 9 and bench_path[9] == document[0].get('Name'):
                                logger.info(f"{current_acc} Profile Loaded")
                                return yaml_inst_list.get('hw_config', {}).get(current_acc)
                    return None

            # Standard single-document format
            yaml_data = yaml.safe_load(f)
            if yaml_data and 'hw_config' in yaml_data:
                hw_config = yaml_data['hw_config'].get(benchname)
                if hw_config:
                    logger.info(f"Loaded hw_config for benchmark: {benchname}")
                    return hw_config
                else:
                    logger.debug(f"No hw_config found for benchmark: {benchname}")
            return None

    except FileNotFoundError:
        logger.warning(f"Config file not found: {config_file}")
        return None
    except yaml.YAMLError as e:
        logger.error(f"YAML parsing error in {config_file}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None


def _instantiate_functional_units(acc, hw_config=None):
    """
    Dynamically instantiate all functional units from registry.

    Args:
        acc: Accelerator SimObject
        hw_config: Optional hw_config dict with FU overrides
    """
    acc.hw_interface.functional_units = FunctionalUnits()

    fu_config = {}
    if hw_config and 'functional_units' in hw_config:
        fu_config = hw_config['functional_units']

    instantiated = 0
    for fu_name, fu_class in _FU_REGISTRY.items():
        try:
            fu_instance = fu_class()

            # Apply any configuration overrides
            if fu_name in fu_config:
                cfg = fu_config[fu_name]
                if 'cycles' in cfg and hasattr(fu_instance, 'cycles'):
                    fu_instance.cycles = cfg['cycles']
                    logger.debug(f"Set {fu_name}.cycles = {cfg['cycles']}")
                if 'limit' in cfg and hasattr(fu_instance, 'limit'):
                    fu_instance.limit = cfg['limit']
                    logger.debug(f"Set {fu_name}.limit = {cfg['limit']}")

            setattr(acc.hw_interface.functional_units, fu_name, fu_instance)
            instantiated += 1
            logger.debug(f"Instantiated FU: {fu_name}")

        except Exception as e:
            logger.warning(f"Failed to instantiate FU {fu_name}: {e}")

    logger.info(f"Instantiated {instantiated}/{len(_FU_REGISTRY)} functional units")


def _instantiate_instructions(acc, hw_config=None):
    """
    Dynamically instantiate all instructions from registry.

    Args:
        acc: Accelerator SimObject
        hw_config: Optional hw_config dict with instruction overrides
    """
    acc.hw_interface.inst_config = InstConfig()

    inst_config = {}
    if hw_config and 'instructions' in hw_config:
        inst_config = hw_config['instructions']

    instantiated = 0
    configured = 0
    for inst_name, inst_class in _INST_REGISTRY.items():
        try:
            inst_instance = inst_class()

            # Apply instruction configuration from hw_config
            # config.yml uses same names as Python (and_inst, or_inst, xor_inst, switch_inst)
            if inst_name in inst_config:
                cfg = inst_config[inst_name]
                if 'functional_unit' in cfg and hasattr(inst_instance, 'functional_unit'):
                    inst_instance.functional_unit = cfg['functional_unit']
                    logger.debug(f"Set {inst_name}.functional_unit = {cfg['functional_unit']}")
                if 'functional_unit_limit' in cfg and hasattr(inst_instance, 'functional_unit_limit'):
                    inst_instance.functional_unit_limit = cfg['functional_unit_limit']
                if 'opcode_num' in cfg and hasattr(inst_instance, 'opcode_num'):
                    inst_instance.opcode_num = cfg['opcode_num']
                configured += 1

            setattr(acc.hw_interface.inst_config, inst_name, inst_instance)
            instantiated += 1
            logger.debug(f"Instantiated instruction: {inst_name}")

        except Exception as e:
            logger.warning(f"Failed to instantiate instruction {inst_name}: {e}")

    logger.info(f"Instantiated {instantiated}/{len(_INST_REGISTRY)} instructions ({configured} configured from hw_config)")


# Name mapping for config.yml -> CycleCounts.py parameters
# Python keywords like 'and', 'or', 'xor' need _inst suffix in CycleCounts
_CYCLE_COUNT_NAME_MAP = {
    'and': 'and_inst',
    'or': 'or_inst',
    'xor': 'xor_inst',
}

def _apply_cycle_counts(acc, hw_config):
    """
    Apply runtime cycle counts from hw_config.

    Args:
        acc: Accelerator SimObject
        hw_config: hw_config dict with instruction cycle counts
    """
    if not hw_config or 'instructions' not in hw_config:
        logger.debug("No instruction cycle counts to apply")
        return

    applied = 0
    for inst_name, inst_cfg in hw_config['instructions'].items():
        if 'runtime_cycles' in inst_cfg:
            try:
                # Map config name to CycleCounts parameter name
                param_name = _CYCLE_COUNT_NAME_MAP.get(inst_name, inst_name)
                setattr(acc.hw_interface.cycle_counts, param_name, inst_cfg['runtime_cycles'])
                applied += 1
                logger.debug(f"Set {param_name} runtime_cycles = {inst_cfg['runtime_cycles']}")
            except Exception as e:
                logger.warning(f"Failed to set cycle count for {inst_name}: {e}")

    if applied > 0:
        logger.info(f"Applied {applied} instruction cycle count overrides")


def AccConfig(acc, bench_file, config_file):
    """
    Configure accelerator with dynamic FU and instruction instantiation.

    Args:
        acc: Accelerator SimObject to configure
        bench_file: Path to benchmark LLVM IR file
        config_file: Path to YAML configuration file
    """
    logger.info(f"Configuring accelerator for: {bench_file}")

    # Initialize LLVMInterface Objects
    acc.llvm_interface = LLVMInterface()
    acc.llvm_interface.in_file = bench_file

    # Extract benchmark information
    M5_Path = os.getenv('M5_PATH')
    benchname = os.path.splitext(os.path.basename(bench_file))[0]
    benchPath = Path(bench_file).parts
    m5PathLen = len(Path(M5_Path).parts) if M5_Path else 0

    logger.debug(f"Benchmark name: {benchname}")
    logger.debug(f"Config file: {config_file}")

    # Initialize HWInterface Objects
    acc.hw_interface = HWInterface()
    acc.hw_interface.cycle_counts = CycleCounts()

    # Load hw_config from YAML (handles mobilenetv2 special case internally)
    hw_config = _load_hw_config(config_file, benchname, benchPath, m5PathLen)

    # Dynamic functional unit instantiation from registry
    _instantiate_functional_units(acc, hw_config)

    # Dynamic instruction instantiation from registry
    _instantiate_instructions(acc, hw_config)

    # Apply cycle count overrides from hw_config
    _apply_cycle_counts(acc, hw_config)

    # Initialize power model and statistics
    acc.hw_interface.salam_power_model = SALAMPowerModel()
    acc.hw_interface.hw_statistics = HWStatistics()
    acc.hw_interface.simulator_config = SimulatorConfig()
    acc.hw_interface.opcodes = InstOpCodes()

    logger.info("AccConfig complete")

#def AccSPMConfig(acc, spm, config_file):
    # Setup config file parser
    #Config = ConfigParser.ConfigParser()
    #Config.read((config_file))
    #Config.sections()
    #def ConfigSectionMap(section):
    #    dict1 = {}
    #    options = Config.options(section)
    #    for option in options:
    #        try:
    #            dict1[option] = Config.get(section, option)
    #            if dict1[option] == -1:
    #                DebugPrint("skip: %s" % option)
    #        except:
    #            print("exception on %s!" % option)
    #            dict1[option] = None
    #    return dict1

    #spm.range = AddrRange(ConfigSectionMap("Memory")['addr_range'], \
    #                      size=ConfigSectionMap("Memory")['size'])
    #spm.latency = ConfigSectionMap("Memory")['latency']
    #spm.conf_table_reported = False
    #spm.ready_mode = Config.getboolean("Memory", 'ready_mode')
    #spm.reset_on_scratchpad_read = Config.getboolean("Memory", 'reset_on_private_read')
    #num_ports = ConfigSectionMap("Memory")['ports']
    #for i in range(int(num_ports)):
    #    acc.spm[i] = spm.spm_ports[i]
