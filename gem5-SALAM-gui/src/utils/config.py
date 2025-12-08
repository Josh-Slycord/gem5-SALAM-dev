"""
Configuration management for gem5-SALAM Installer.
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class InstallConfig:
    """Installation configuration."""
    gem5_path: str = ""
    wsl_distro: str = ""
    build_type: str = "opt"
    parallel_jobs: Optional[int] = None
    llvm_version: int = 14

    # Component installation flags
    install_build_essentials: bool = True
    install_python: bool = True
    install_llvm: bool = True
    install_arm_toolchain: bool = True
    install_gem5_deps: bool = True
    install_multilib: bool = True


@dataclass
class AppSettings:
    """Application settings."""
    last_gem5_path: str = ""
    last_distro: str = ""
    window_geometry: Optional[str] = None
    theme: str = "dark"


class ConfigManager:
    """Manages application configuration and settings."""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            # Default to user's home directory
            config_dir = Path.home() / ".gem5-salam-installer"

        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.settings_file = self.config_dir / "settings.json"
        self.install_config_file = self.config_dir / "install_config.yaml"

    def load_settings(self) -> AppSettings:
        """Load application settings."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                return AppSettings(**data)
            except Exception:
                pass
        return AppSettings()

    def save_settings(self, settings: AppSettings):
        """Save application settings."""
        with open(self.settings_file, 'w') as f:
            json.dump(asdict(settings), f, indent=2)

    def load_install_config(self) -> InstallConfig:
        """Load installation configuration."""
        if self.install_config_file.exists():
            try:
                with open(self.install_config_file, 'r') as f:
                    data = yaml.safe_load(f)
                if data:
                    return InstallConfig(**data)
            except Exception:
                pass
        return InstallConfig()

    def save_install_config(self, config: InstallConfig):
        """Save installation configuration."""
        with open(self.install_config_file, 'w') as f:
            yaml.dump(asdict(config), f, default_flow_style=False)

    def get_recent_paths(self) -> list[str]:
        """Get list of recently used gem5 paths."""
        recent_file = self.config_dir / "recent_paths.json"
        if recent_file.exists():
            try:
                with open(recent_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def add_recent_path(self, path: str, max_entries: int = 10):
        """Add a path to recent paths list."""
        recent = self.get_recent_paths()

        # Remove if already exists, add to front
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)

        # Limit entries
        recent = recent[:max_entries]

        recent_file = self.config_dir / "recent_paths.json"
        with open(recent_file, 'w') as f:
            json.dump(recent, f)
