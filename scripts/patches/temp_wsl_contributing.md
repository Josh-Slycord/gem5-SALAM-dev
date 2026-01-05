# WSL Environment Guide

This document provides guidelines for working in the WSL (Ubuntu-20.04) environment.

## Environment Info

- **Distribution**: Ubuntu-20.04
- **User**: jslycord
- **Home**: `/home/jslycord`
- **Windows Mount**: `/mnt/c/Users/Local_Only_Slycord`

---

## Projects in This Environment

| Project | Path | Description |
|---------|------|-------------|
| gem5-SALAM | `~/gem5-SALAM-dev` | Hardware accelerator simulator |

---

## Path Conventions

### WSL Paths
```bash
/home/jslycord/                    # Home directory
/home/jslycord/gem5-SALAM-dev/     # gem5-SALAM project
```

### Accessing Windows Files
```bash
/mnt/c/Users/Local_Only_Slycord/   # Windows home
/mnt/c/Users/Local_Only_Slycord/.claude/plans/  # Claude plan files
```

### From Windows (accessing WSL)
```powershell
wsl -d Ubuntu-20.04 -- bash -c 'command'
\\wsl$\Ubuntu-20.04\home\jslycord\  # File explorer path
```

---

## Environment Variables

Add to `~/.bashrc`:
```bash
# gem5-SALAM
export M5_PATH=/home/jslycord/gem5-SALAM-dev

# Optional: Add scripts to PATH
export PATH=$PATH:$M5_PATH/scripts
```

Reload:
```bash
source ~/.bashrc
```

---

## Common Commands

### WSL Management (from Windows)
```powershell
wsl -d Ubuntu-20.04              # Enter WSL
wsl --shutdown                   # Restart WSL (fixes display issues)
wsl -l -v                        # List distributions
```

### GUI Applications
WSLg should handle display automatically. If issues:
```bash
# Check display
echo $DISPLAY

# Manual (with VcXsrv on Windows)
export DISPLAY=$(grep nameserver /etc/resolv.conf | awk '{print $2}'):0
```

---

## File Operations

### Copying Between Windows and WSL
```bash
# Windows → WSL
cp /mnt/c/Users/Local_Only_Slycord/file.txt ~/

# WSL → Windows
cp ~/file.txt /mnt/c/Users/Local_Only_Slycord/
```

### Permissions
WSL files on Windows mounts may have permission issues:
```bash
# Fix permissions on WSL-native files
chmod 755 script.sh

# Windows files are typically 777
```

---

## Development Workflow

### 1. Start Session
```bash
# Enter WSL
wsl -d Ubuntu-20.04

# Navigate to project
cd ~/gem5-SALAM-dev
```

### 2. Check Status
```bash
git status
```

### 3. Work on Code
- Edit files in WSL or via VS Code Remote-WSL
- Build and test in WSL terminal

### 4. Commit Changes
```bash
git add .
git commit -m "feat: description"
```

---

## Installed Tools

### Build Tools
- GCC/G++ (build-essential)
- SCons
- Make
- ARM cross-compiler (arm-linux-gnueabi-gcc)

### Python
- Python 3.8+
- pip
- PySide6 (for GUI)

### Optional
- Doxygen (C++ docs)
- Sphinx (Python docs)

### Install Missing Tools
```bash
sudo apt update
sudo apt install build-essential scons
pip install PySide6 pyqtgraph networkx
```

---

## Troubleshooting

### GUI Not Launching
```powershell
# From Windows PowerShell (admin)
wsl --shutdown
# Then reopen WSL terminal
```

### Display Errors
```bash
# Check if WSLg is working
echo $DISPLAY
# Should show something like :0

# If empty, try:
export DISPLAY=:0
```

### Permission Denied
```bash
chmod +x script.sh
```

### Out of Disk Space
```powershell
# Check WSL disk usage
wsl -d Ubuntu-20.04 -- df -h
```

---

## Coordination with Windows Environment

### Plan Files
Claude instances coordinate via plan files at:
```
/mnt/c/Users/Local_Only_Slycord/.claude/plans/
```

### Protocol
1. Check for existing plan files before modifying shared files
2. Create status file when working on significant changes
3. Update status periodically
4. Clean up when done

### Status File Format
```markdown
# Instance Status: [description]

## Files Being Modified
- /home/jslycord/gem5-SALAM-dev/path/to/file

## Current Task
Description of work

## Status
- [x] Completed step
- [ ] In progress step

## Last Updated
YYYY-MM-DD HH:MM
```

---

## Project-Specific Guides

See individual project CONTRIBUTING.md files:
- `~/gem5-SALAM-dev/CONTRIBUTING.md` - gem5-SALAM project

---

## Quick Reference

| Task | Command |
|------|---------|
| Enter WSL | `wsl -d Ubuntu-20.04` |
| Restart WSL | `wsl --shutdown` (then reopen) |
| gem5-SALAM dir | `cd ~/gem5-SALAM-dev` |
| Build gem5 | `scons build/ARM/gem5.opt -j$(nproc)` |
| Launch GUI | `python -m scripts.salam_gui` |
| Generate docs | `python scripts/generate_docs.py` |
| Windows home | `/mnt/c/Users/Local_Only_Slycord` |
