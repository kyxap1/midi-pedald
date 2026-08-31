"""Frozen-binary entry point. PyInstaller runs this as __main__, so the import
must be absolute - midi_pedald/__main__.py's relative import does not survive
freezing."""
import sys

from midi_pedald.cli import main

sys.exit(main())
