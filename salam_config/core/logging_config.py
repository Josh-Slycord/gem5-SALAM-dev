"""
Unified logging infrastructure for gem5-SALAM configuration system.

Provides:
- Centralized logging configuration
- File-based logging with rotation
- Console logging with color support
- Context-aware log formatting
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


class ColorFormatter(logging.Formatter):
    """Custom formatter with color support for console output."""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }

    def __init__(self, fmt: str, use_colors: bool = True):
        super().__init__(fmt)
        self.use_colors = use_colors and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        if self.use_colors:
            levelname = record.levelname
            if levelname in self.COLORS:
                record.levelname = (
                    f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
                )
        return super().format(record)


class SALAMLogger:
    """
    Centralized logging for gem5-SALAM configuration system.

    Singleton class that provides unified logging across all modules.
    Supports both file and console output with configurable levels.
    """

    _instance: Optional['SALAMLogger'] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not SALAMLogger._initialized:
            self._setup()
            SALAMLogger._initialized = True

    def _setup(self):
        """Initialize logging configuration."""
        self.root = logging.getLogger("salam")
        self.root.setLevel(logging.DEBUG)

        # Prevent duplicate handlers
        if self.root.handlers:
            return

        # Create log directory
        self.log_dir = Path.home() / ".salam" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # File handler with rotation
        log_file = self.log_dir / f"salam_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)

        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = ColorFormatter(
            '[%(levelname)s] %(name)s: %(message)s'
        )
        console_handler.setFormatter(console_formatter)

        self.root.addHandler(file_handler)
        self.root.addHandler(console_handler)

        # Log startup
        self.root.debug(f"SALAM logging initialized. Log file: {log_file}")

    def get_logger(self, name: str) -> logging.Logger:
        """
        Get a logger for the specified module.

        Args:
            name: Module name (will be prefixed with 'salam.')

        Returns:
            Logger instance for the module
        """
        return logging.getLogger(f"salam.{name}")

    def set_level(self, level: str):
        """
        Set the root logger level.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        if level.upper() in level_map:
            self.root.setLevel(level_map[level.upper()])

    def set_console_level(self, level: str):
        """
        Set the console handler level.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        if level.upper() in level_map:
            for handler in self.root.handlers:
                if isinstance(handler, logging.StreamHandler) and \
                   not isinstance(handler, logging.FileHandler):
                    handler.setLevel(level_map[level.upper()])

    def get_log_file(self) -> Path:
        """Get the current log file path."""
        return self.log_dir / f"salam_{datetime.now().strftime('%Y%m%d')}.log"


# Convenience function for module-level logging
def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for the specified module.

    Args:
        name: Module name

    Returns:
        Logger instance
    """
    return SALAMLogger().get_logger(name)
