#!/usr/bin/env python3
"""
Entry point for gem5-SALAM GUI.

Usage:
    python -m salam_gui                          # Launch GUI
    python -m salam_gui --load m5out/            # Load simulation output
    python -m salam_gui --connect localhost:5555 # Real-time mode
"""


__version__ = "3.0.0.pre[1.0.0]"

import sys
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description='gem5-SALAM GUI - Hardware Accelerator Visualization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    python -m salam_gui
    python -m salam_gui --load /path/to/m5out
    python -m salam_gui --cdfg cdfg.dot
'''
    )

    parser.add_argument(
        '--load', '-l',
        type=str,
        help='Load simulation output directory'
    )
    parser.add_argument(
        '--cdfg', '-c',
        type=str,
        help='Load CDFG dot file directly'
    )
    parser.add_argument(
        '--stats', '-s',
        type=str,
        help='Load statistics file directly'
    )
    parser.add_argument(
        '--connect',
        type=str,
        metavar='HOST:PORT',
        help='Connect to running simulation (real-time mode)'
    )
    parser.add_argument(
        '--dark',
        action='store_true',
        help='Use dark theme'
    )

    args = parser.parse_args()

    # Import here to avoid slow startup for --help
    from .app import SALAMGuiApp

    app = SALAMGuiApp(sys.argv)

    # Apply theme
    if args.dark:
        app.set_dark_theme()

    # Create main window
    from .main_window import MainWindow
    window = MainWindow()

    # Handle startup arguments
    if args.load:
        window.load_simulation_output(Path(args.load))
    if args.cdfg:
        window.load_cdfg(Path(args.cdfg))
    if args.stats:
        window.load_stats(Path(args.stats))
    if args.connect:
        window.connect_live(args.connect)

    window.show()

    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
