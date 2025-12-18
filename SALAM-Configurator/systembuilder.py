#!/usr/bin/env python3
# ==============================================================================
# systembuilder.py - gem5-SALAM System Configuration Generator
# ==============================================================================
"""SALAM System Builder - Accelerator Configuration Generator.

This script generates gem5-SALAM configuration files from YAML specifications.
It parses benchmark configuration files and produces Python configs for gem5
simulations and C header files for benchmark code.

Generated Files:
    | File                 | Purpose                              |
    |----------------------|--------------------------------------|
    | <name>.py            | Accelerator cluster configuration    |
    | fs_<name>.py         | Full-system simulation configuration |
    | <cluster>_hw_defines.h | C header with memory-mapped addresses|

Usage:
    ./systembuilder.py --sysName NAME --benchDir PATH [--dry-run] [--validate-only]

Arguments:
    --sysName       Name for generated configuration files
    --benchDir      Path to benchmark directory (relative to M5_PATH)
    --path          M5_PATH override (optional)
    --output-dir    Alternate output directory (optional)
    --dry-run       Preview without writing files
    --validate-only Compare generated files against existing
    --base-address  Base address for accelerator (default: 0x10020000)

Configuration (config.yml) Format:
    acc_cluster:
      - Name: cluster_name
      - DMA:
          Type: NonCoherent
          ...
      - Accelerator:
          Name: acc_name
          ...

Example:
    Generate FFT benchmark configuration:
        ./systembuilder.py --sysName fft --benchDir benchmarks/fft

    Validate existing configuration:
        ./systembuilder.py --sysName fft --benchDir benchmarks/fft --validate-only

See Also:
    - SALAMClassGenerator.py: Functional unit class generator
    - parser.py: YAML config parsing utilities
    - fs_template.py: Full-system configuration template
"""


__version__ = "3.0.0.pre[1.0.0]"

# Import needed packages
import yaml
import os
import textwrap
import shutil
import argparse
import tempfile
import difflib
from parser import *

# This requires M5_PATH to point to your gem5-SALAM directory
M5_Path = os.getenv("M5_PATH")

# Define the imports of the gem5 script
imports = """import m5
from m5.objects import *
from m5.util import *
from configparser import ConfigParser
from HWAccConfig import *

"""
# L1 Cache defined here for now, need to add some more configurability to this
l1Cache = """class L1Cache(Cache):
    assoc = 2
    tag_latency = 2
    data_latency = 2
    response_latency = 2
    mshrs = 4
    tgts_per_mshr = 20

    def __init__(self, size, options=None):
        self.size = size
        super(L1Cache, self).__init__()
        pass

"""

# Parse Arguements
parser = argparse.ArgumentParser(description="SALAM System Builder")
parser.add_argument("--sysName", help="Desired gem5 script name", required=True)
parser.add_argument(
    "--benchDir", help="Path to Benchmark Directory Relative to M5_PATH", required=True
)
parser.add_argument("--path", help="Path to M5 Directory", required=False)
parser.add_argument(
    "--output-dir", dest="output_dir", help="Alternate output directory", required=False
)
parser.add_argument(
    "--dry-run",
    dest="dry_run",
    action="store_true",
    help="Preview without writing files",
)
parser.add_argument(
    "--validate-only",
    dest="validate_only",
    action="store_true",
    help="Compare against existing files",
)
parser.add_argument(
    "--base-address",
    dest="base_address",
    type=lambda x: int(x, 0),
    default=0x10020000,
    help="Base address for accelerator cluster (default: 0x10020000)",
)
args = parser.parse_args()

if M5_Path is None:
    print("Looking for Path Argument from Command Line")
    M5_Path = args.path
    if M5_Path is None:
        print("M5_PATH Not Found")
        exit(1)

# Set file information
fileName = args.sysName
workingDirectory = M5_Path + "/" + args.benchDir + "/"

# Set output paths based on mode
temp_dir = None
if args.output_dir:
    CONFIG_Path = args.output_dir + "/configs/SALAM/generated/"
    HEADER_Path = args.output_dir + "/" + args.benchDir + "/"
    os.makedirs(CONFIG_Path, exist_ok=True)
    os.makedirs(HEADER_Path, exist_ok=True)
elif args.validate_only:
    temp_dir = tempfile.mkdtemp(prefix="salam_validate_")
    CONFIG_Path = temp_dir + "/configs/SALAM/generated/"
    HEADER_Path = temp_dir + "/" + args.benchDir + "/"
    os.makedirs(CONFIG_Path, exist_ok=True)
    os.makedirs(HEADER_Path, exist_ok=True)
else:
    CONFIG_Path = M5_Path + "/configs/SALAM/generated/"
    HEADER_Path = workingDirectory

files_to_write = {}


def write_file(path, content, description=""):
    if args.dry_run:
        files_to_write[path] = content
        print(f"[DRY-RUN] Would write: {path} ({description})")
    else:
        with open(path, "w") as f:
            f.write(content) if isinstance(content, str) else f.writelines(content)
        print(f"Wrote: {path}")


def compare_files(new_path, old_path, name):
    try:
        with open(old_path, "r") as f:
            old_content = f.readlines()
    except FileNotFoundError:
        print(f"[NEW] {name}: No existing file at {old_path}")
        return False
    with open(new_path, "r") as f:
        new_content = f.readlines()
    diff = list(
        difflib.unified_diff(
            old_content,
            new_content,
            fromfile=f"existing/{name}",
            tofile=f"generated/{name}",
        )
    )
    if diff:
        print(f"[DIFF] {name}:")
        for line in diff[:50]:
            print(f"  {line.rstrip()}")
        if len(diff) > 50:
            print(f"  ... and {len(diff) - 50} more lines")
        return False
    else:
        print(f"[OK] {name}: Matches existing file")
        return True


def main():
    global temp_dir
    baseAddress = (
        args.base_address
    )  # Configurable via --base-address (default: 0x10020000)
    maxAddress = 0x13FFFFFF
    configPath = workingDirectory + "config.yml"

    if baseAddress != 0x10020000:
        print(f"Using custom base address: {hex(baseAddress)}")

    stream = open(configPath, "r")
    config = yaml.load_all(stream, Loader=yaml.FullLoader)
    baseAddress, clusters = parseYAMLFile(config, configPath, baseAddress)

    if args.dry_run:
        print("\n=== DRY RUN MODE ===")
        print(f"Would generate files for: {fileName}")
        print(f"Config path: {configPath}")
        print(f"Clusters: {[c.name for c in clusters]}\n")

    genConfigFile(clusters)
    headerList = parseOriginalHeader(clusters)
    genHeaderFiles(headerList, clusters)
    genFullSystemFile(clusters)

    if args.validate_only:
        print("\n=== VALIDATION RESULTS ===")
        all_match = True
        gen_config = CONFIG_Path + fileName + ".py"
        orig_config = M5_Path + "/configs/SALAM/generated/" + fileName + ".py"
        if not compare_files(gen_config, orig_config, fileName + ".py"):
            all_match = False
        gen_fs = CONFIG_Path + "fs_" + fileName + ".py"
        orig_fs = M5_Path + "/configs/SALAM/generated/fs_" + fileName + ".py"
        if not compare_files(gen_fs, orig_fs, "fs_" + fileName + ".py"):
            all_match = False
        for cluster in clusters:
            header_name = cluster.name + "_hw_defines.h"
            gen_header = HEADER_Path + header_name
            orig_header = workingDirectory + header_name
            if not compare_files(gen_header, orig_header, header_name):
                all_match = False
        if temp_dir:
            shutil.rmtree(temp_dir)
        if all_match:
            print("\n[SUCCESS] All generated files match existing files")
            return 0
        else:
            print("\n[WARNING] Some files differ from existing versions")
            return 1

    if args.dry_run:
        print("\n=== FILES THAT WOULD BE WRITTEN ===")
        for path in files_to_write:
            print(f"  {path}")

    if clusters[-1].clusterTopAddress > maxAddress:
        print("WARNING: Address range is greater than defined for gem5")


def parseYAMLFile(config, configPath, baseAddress):
    clusters = []
    for clusterList in config:
        clusterName = None
        dmas = []
        accs = []
        for listType, devices in clusterList.items():
            if listType == "acc_cluster":
                for device in devices:
                    if "Name" in device:
                        clusterName = device["Name"]
                    if "DMA" in device:
                        dmas.append(device)
                    if "Accelerator" in device:
                        accs.append(device)
        clusters.append(
            AccCluster(clusterName, dmas, accs, baseAddress, M5_Path, configPath)
        )
        baseAddress = clusters[-1].clusterTopAddress + (
            64 - (int(clusters[-1].clusterTopAddress) % 64)
        )
        if (int(baseAddress) % 64) != 0:
            print("Address Alignment Error: " + hex(baseAddress))
    return baseAddress, clusters


def genConfigFile(clusters):
    content = []
    # Add module-level documentation
    content.append(
        "# ==============================================================================\n"
    )
    content.append("# " + fileName + ".py - Auto-Generated Accelerator Configuration\n")
    content.append(
        "# ==============================================================================\n"
    )
    content.append('"""Auto-Generated Accelerator Cluster Configuration.\n\n')
    content.append("WARNING: This file is auto-generated by systembuilder.py.\n")
    content.append("         DO NOT MODIFY DIRECTLY - changes will be overwritten.\n")
    content.append(
        "         Regenerate using: ./systembuilder.py --sysName "
        + fileName
        + " --benchDir ...\n\n"
    )
    content.append("Clusters defined:\n")
    for cluster in clusters:
        content.append("    - " + cluster.name + "\n")
    content.append("\nThis module provides:\n")
    content.append("    - L1Cache: Cache configuration for accelerator\n")
    content.append("    - build<Cluster>(): Setup function for each cluster\n")
    content.append("    - makeHWAcc(): Top-level accelerator setup function\n")
    content.append('"""\n\n')
    content.append(imports)
    content.append(l1Cache)
    for cluster in clusters:
        for line in cluster.genConfig():
            content.append(line + "\n")
        for dma in cluster.dmas:
            for line in dma.genConfig():
                content.append("\t" + line + "\n")
        for acc in cluster.accs:
            for line in acc.genDefinition():
                content.append("\t" + line + "\n")
        for acc in cluster.accs:
            for line in acc.genConfig():
                content.append("\t" + line + "\n")
    content.append("def makeHWAcc(args, system):\n\n")
    for i in clusters:
        content.append("\tsystem." + i.name.lower() + " = AccCluster()" + "\n")
        content.append(
            "\tbuild" + i.name + "(args, system, system." + i.name.lower() + ")\n\n"
        )
    output_path = CONFIG_Path + fileName + ".py"
    write_file(output_path, "".join(content), "accelerator config")


def parseOriginalHeader(clusters):
    headerList = []
    for cluster in clusters:
        try:
            f = open(workingDirectory + cluster.name + "_hw_defines.h", "r")
            oldHeader = f.readlines()
            f.close()
            begin = None
            end = None
            for i in range(0, len(oldHeader)):
                if oldHeader[i] == "//BEGIN GENERATED CODE\n":
                    begin = i
                elif (
                    oldHeader[i] == "//END GENERATED CODE\n"
                    or oldHeader[i] == "//END GENERATED CODE"
                ):
                    end = i
            if begin is not None and end is not None:
                del oldHeader[begin : end + 1]
            headerList.append(oldHeader)
        except:
            print("No Header Found for " + cluster.name)
            headerList.append([])
    return headerList


def genHeaderFiles(headerList, clusters):
    # Fixed to iterate correctly (was nested loop bug)
    for idx, cluster in enumerate(clusters):
        currentHeader = list(headerList[idx]) if idx < len(headerList) else []
        # Add Doxygen documentation block at the start of generated section
        currentHeader.append("//BEGIN GENERATED CODE\n")
        currentHeader.append("/**\n")
        currentHeader.append(" * @file " + cluster.name + "_hw_defines.h\n")
        currentHeader.append(
            " * @brief Memory-mapped register addresses for "
            + cluster.name
            + " cluster\n"
        )
        currentHeader.append(" *\n")
        currentHeader.append(" * @warning GENERATED CODE - DO NOT MODIFY\n")
        currentHeader.append(" *          Regenerate using: ./systembuilder.py\n")
        currentHeader.append(" *\n")
        currentHeader.append(
            " * These defines provide the memory-mapped addresses for accessing\n"
        )
        currentHeader.append(
            " * DMA controllers, accelerators, and scratchpad memory in the\n"
        )
        currentHeader.append(" * gem5-SALAM simulation environment.\n")
        currentHeader.append(" */\n")
        currentHeader.append("//Cluster: " + cluster.name.upper() + "\n")
        for dma in cluster.dmas:
            if dma.dmaType == "NonCoherent":
                currentHeader.append("//" + dma.dmaType + "DMA" + "\n")
                currentHeader.append(
                    "#define " + dma.name.upper() + "_Flags " + hex(dma.address) + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_RdAddr "
                    + hex(dma.address + 1)
                    + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_WrAddr "
                    + hex(dma.address + 9)
                    + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_CopyLen "
                    + hex(dma.address + 17)
                    + "\n"
                )
            elif dma.dmaType == "Stream":
                currentHeader.append("//" + dma.dmaType + "DMA" + "\n")
                currentHeader.append(
                    "#define " + dma.name.upper() + "_Flags " + hex(dma.address) + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_RdAddr "
                    + hex(dma.address + 4)
                    + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_WrAddr "
                    + hex(dma.address + 12)
                    + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_RdFrameSize "
                    + hex(dma.address + 20)
                    + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_NumRdFrames "
                    + hex(dma.address + 24)
                    + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_RdFrameBufSize "
                    + hex(dma.address + 25)
                    + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_WrFrameSize "
                    + hex(dma.address + 26)
                    + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_NumWrFrames "
                    + hex(dma.address + 30)
                    + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_WrFrameBufSize "
                    + hex(dma.address + 31)
                    + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_Stream "
                    + hex(dma.address + 32)
                    + "\n"
                )
                currentHeader.append(
                    "#define "
                    + dma.name.upper()
                    + "_Status "
                    + hex(dma.statusAddress)
                    + "\n"
                )
        for acc in cluster.accs:
            currentHeader.append("//Accelerator: " + acc.name.upper() + "\n")
            currentHeader.append(
                "#define " + acc.name.upper() + " " + hex(acc.address) + "\n"
            )
            for var in acc.variables:
                if "Cache" in var.type:
                    continue
                elif "Stream" in var.type:
                    currentHeader.append(
                        "#define " + var.name + " " + hex(var.address) + "\n"
                    )
                    currentHeader.append(
                        "#define "
                        + var.name
                        + "_Status "
                        + hex(var.statusAddress)
                        + "\n"
                    )
                else:
                    currentHeader.append(
                        "#define " + var.name + " " + hex(var.address) + "\n"
                    )
        currentHeader.append("//END GENERATED CODE\n")
        output_path = HEADER_Path + cluster.name + "_hw_defines.h"
        write_file(output_path, "".join(currentHeader), f"header for {cluster.name}")


def genFullSystemFile(clusters):
    template_path = M5_Path + "/SALAM-Configurator/fs_template.py"
    output_path = CONFIG_Path + "fs_" + fileName + ".py"

    if args.dry_run:
        files_to_write[output_path] = "[full system file content]"
        print(f"[DRY-RUN] Would write: {output_path} (full system config)")
        return

    shutil.copyfile(template_path, output_path)
    f = open(output_path, "r")
    fullSystem = f.readlines()
    f.close()
    fullSystem[65] = "import " + fileName + "\n"
    fullSystem[229] = "        " + fileName + ".makeHWAcc(args, test_sys)\n"
    with open(output_path, "w") as f:
        f.writelines(fullSystem)
    print(f"Wrote: {output_path}")


def writeLines(writer, lines):
    for line in lines:
        writer.write("\t" + line + "\n")


if __name__ == "__main__":
    exit(main() or 0)
