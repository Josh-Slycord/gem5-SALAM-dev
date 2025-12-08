"""
WSL (Windows Subsystem for Linux) detection and interaction utilities.
"""

import subprocess
import re
from dataclasses import dataclass
from typing import Optional, List, Dict
from pathlib import Path


@dataclass
class WSLDistro:
    """Represents a WSL distribution."""
    name: str
    is_default: bool
    version: int  # WSL 1 or 2
    state: str  # Running, Stopped, etc.


@dataclass
class WSLStatus:
    """Overall WSL status."""
    installed: bool
    version: Optional[str]
    distros: List[WSLDistro]
    default_distro: Optional[str]
    error: Optional[str] = None


def check_wsl_installed() -> bool:
    """Check if WSL is installed and available."""
    try:
        result = subprocess.run(
            ["wsl", "--status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        return False


def get_wsl_version() -> Optional[str]:
    """Get the WSL version information."""
    try:
        result = subprocess.run(
            ["wsl", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def list_distros() -> List[WSLDistro]:
    """List all installed WSL distributions."""
    distros = []
    try:
        result = subprocess.run(
            ["wsl", "--list", "--verbose"],
            capture_output=True,
            timeout=10
        )
        if result.returncode != 0:
            return distros

        # WSL outputs UTF-16 LE encoded text
        try:
            output = result.stdout.decode('utf-16-le')
        except UnicodeDecodeError:
            output = result.stdout.decode('utf-8', errors='ignore')

        lines = output.strip().split('\n')

        # Skip header line
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue

            # Parse line: "* Ubuntu    Running    2" or "  Debian    Stopped    1"
            is_default = line.startswith('*')
            line = line.lstrip('* ')

            # Split by whitespace
            parts = line.split()
            if len(parts) >= 3:
                name = parts[0]
                state = parts[1]
                try:
                    version = int(parts[2])
                except ValueError:
                    version = 2

                distros.append(WSLDistro(
                    name=name,
                    is_default=is_default,
                    version=version,
                    state=state
                ))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return distros


def get_wsl_status() -> WSLStatus:
    """Get comprehensive WSL status."""
    installed = check_wsl_installed()

    if not installed:
        return WSLStatus(
            installed=False,
            version=None,
            distros=[],
            default_distro=None,
            error="WSL is not installed or not available"
        )

    version = get_wsl_version()
    distros = list_distros()
    default_distro = next((d.name for d in distros if d.is_default), None)

    return WSLStatus(
        installed=True,
        version=version,
        distros=distros,
        default_distro=default_distro
    )


def run_in_wsl(
    command: str,
    distro: Optional[str] = None,
    working_dir: Optional[str] = None,
    timeout: Optional[int] = None
) -> subprocess.CompletedProcess:
    """
    Run a command inside WSL.

    Args:
        command: The bash command to run
        distro: Specific distro to use (None for default)
        working_dir: Working directory (Windows path, will be converted)
        timeout: Timeout in seconds

    Returns:
        CompletedProcess with stdout/stderr
    """
    wsl_cmd = ["wsl"]

    if distro:
        wsl_cmd.extend(["-d", distro])

    if working_dir:
        # Convert Windows path to WSL path
        wsl_path = windows_to_wsl_path(working_dir)
        command = f"cd '{wsl_path}' && {command}"

    wsl_cmd.extend(["-e", "bash", "-c", command])

    return subprocess.run(
        wsl_cmd,
        capture_output=True,
        text=True,
        timeout=timeout
    )


def run_in_wsl_streaming(
    command: str,
    distro: Optional[str] = None,
    working_dir: Optional[str] = None
) -> subprocess.Popen:
    """
    Run a command inside WSL with streaming output.

    Returns a Popen object for reading stdout/stderr incrementally.
    """
    wsl_cmd = ["wsl"]

    if distro:
        wsl_cmd.extend(["-d", distro])

    if working_dir:
        wsl_path = windows_to_wsl_path(working_dir)
        command = f"cd '{wsl_path}' && {command}"

    wsl_cmd.extend(["-e", "bash", "-c", command])

    return subprocess.Popen(
        wsl_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1  # Line buffered
    )


def windows_to_wsl_path(windows_path: str) -> str:
    """Convert a Windows path to WSL path."""
    path = Path(windows_path)

    # Handle drive letter
    if path.drive:
        drive_letter = path.drive[0].lower()
        rest_of_path = str(path)[2:].replace('\\', '/')
        return f"/mnt/{drive_letter}{rest_of_path}"

    # Already a Unix-style path or relative
    return str(path).replace('\\', '/')


def wsl_to_windows_path(wsl_path: str) -> str:
    """Convert a WSL path to Windows path."""
    if wsl_path.startswith('/mnt/'):
        # /mnt/c/Users/... -> C:\Users\...
        parts = wsl_path[5:].split('/', 1)
        drive = parts[0].upper()
        rest = parts[1] if len(parts) > 1 else ''
        windows_path = rest.replace("/", "\\")
        return drive + ":\\" + windows_path

    return wsl_path


def check_command_exists(command: str, distro: Optional[str] = None) -> bool:
    """Check if a command exists in WSL."""
    try:
        result = run_in_wsl(f"command -v {command}", distro=distro, timeout=10)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def get_distro_info(distro: Optional[str] = None) -> dict:
    """Get information about the WSL distro (OS, version, etc.)."""
    info = {}

    try:
        # Get OS info
        result = run_in_wsl("cat /etc/os-release", distro=distro, timeout=10)
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    info[key] = value.strip('"')
    except subprocess.TimeoutExpired:
        pass

    return info


def check_dependencies(distro: Optional[str] = None) -> Dict[str, bool]:
    """Check which gem5-SALAM dependencies are installed."""
    dependencies = {
        'build-essential': 'g++',
        'python3': 'python3',
        'pip': 'pip3',
        'scons': 'scons',
        'git': 'git',
        'make': 'make',
        'clang': 'clang',
        'llvm': 'llvm-config',
        'arm-none-eabi-gcc': 'arm-none-eabi-gcc',
    }

    results = {}
    for name, cmd in dependencies.items():
        results[name] = check_command_exists(cmd, distro)

    return results


def is_windows_terminal_available() -> bool:
    """Check if Windows Terminal (wt.exe) is available."""
    try:
        result = subprocess.run(
            ["where", "wt"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def launch_in_terminal(
    command: str,
    distro: Optional[str] = None,
    title: str = "gem5-SALAM Installer",
    wait_for_completion: bool = True
) -> subprocess.Popen:
    """
    Launch a command in Windows Terminal with WSL.

    This allows interactive sudo password prompts to work.

    Args:
        command: The bash command to run in WSL
        distro: Specific distro to use (None for default)
        title: Window title for the terminal
        wait_for_completion: If True, add a pause at the end

    Returns:
        Popen object for the terminal process
    """
    import tempfile

    # Create a temporary script file to avoid quoting issues
    # Write it to Windows temp and access via /mnt/c/...
    temp_dir = Path(tempfile.gettempdir())
    script_file = temp_dir / "gem5_salam_terminal_cmd.sh"

    # Build the script content
    script_content = "#!/bin/bash\n"
    script_content += command + "\n"
    if wait_for_completion:
        script_content += 'echo ""\n'
        script_content += 'echo "Press Enter to close..."\n'
        script_content += "read\n"

    # Write script with Unix line endings
    with open(script_file, 'w', newline='\n') as f:
        f.write(script_content)

    # Convert to WSL path
    wsl_script_path = windows_to_wsl_path(str(script_file))

    # Build terminal command
    if is_windows_terminal_available():
        distro_arg = f"-d {distro}" if distro else ""
        terminal_cmd_str = f'wt -w 0 new-tab --title "{title}" wsl {distro_arg} bash {wsl_script_path}'

        return subprocess.Popen(
            terminal_cmd_str,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    else:
        # Fallback to cmd.exe with wsl
        distro_arg = f"-d {distro}" if distro else ""
        terminal_cmd_str = f'start "{title}" wsl {distro_arg} bash {wsl_script_path}'

        return subprocess.Popen(
            terminal_cmd_str,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )


def create_install_wrapper_script(
    script_path: str,
    marker_file: str
) -> str:
    """
    Create a wrapper command that runs a script and creates a marker file on completion.

    Args:
        script_path: WSL path to the script to run
        marker_file: WSL path to marker file to create on success

    Returns:
        The wrapper command string
    """
    # Create a command that:
    # 1. Strips CRLF and runs the script
    # 2. Captures the exit code
    # 3. Creates a marker file with success/failure
    wrapper = f"""
    EXIT_CODE=0
    tr -d '\\r' < '{script_path}' | bash
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "SUCCESS" > '{marker_file}'
    else
        echo "FAILED:$EXIT_CODE" > '{marker_file}'
    fi
    exit $EXIT_CODE
    """
    # Compress to single line for shell execution
    return wrapper.replace('\n', ' ').strip()
