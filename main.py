#!/usr/bin/env python3
"""
main.py
-------
Entry point for Label Cutter Screen.

Usage:
    python3 main.py                     # uses ~/labelcutter_screen/config.json
    python3 main.py --config /path.json # custom config location
    python3 main.py --windowed          # force windowed (ignore fullscreen setting)
"""
import argparse
import sys

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from config import Config
from ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="Label Cutter Screen")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--windowed", action="store_true",
                         help="Force windowed mode, ignoring config fullscreen setting")
    args = parser.parse_args()

    config = Config(args.config)
    if args.windowed:
        config.set(False, "screen", "fullscreen")

    app = Gtk.Application(application_id="com.labelcutter.screen")

    def on_activate(application):
        win = MainWindow(application, config)
        win.show_all()

    app.connect("activate", on_activate)
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
