#!/usr/bin/env python3
"""Entry point for YAHT (Yet Another Hdf5 Tool).

Usually launched via scripts/run.sh or scripts/run.bat, which set up a
venv first. To run directly instead, from the repository root:
    python src/run.py [path/to/file.h5 ...] [path/to/directory ...]
No sys.path setup needed here -- running a script directly puts its own
directory (src/, alongside app.py and friends) at the front of sys.path.

Any number of paths can be given, mixing individual .h5 files and
directories -- each directory is expanded to every .h5 file directly
inside it (see App.open_paths). With no arguments, starts with nothing
open; use File > Open File.
"""
import sys

from app import main

if __name__ == "__main__":
    main(sys.argv[1:] or None)
