# YAHT

**Y**et **A**nother **H**df5 **T**ool — a modern, cross-platform desktop
viewer for HDF5 (`.h5`) files, built with
[PySide6 (Qt for Python)](https://doc.qt.io/qtforpython-6/) and
[h5py](https://www.h5py.org/).

- Left pane: a VS Code-style explorer over the file's group hierarchy —
  expand/collapse groups, lazily loading children as you go.
- Right pane: select a group to see its attributes and contents, or select
  a dataset to open it as a table.
- The table view scrolls continuously over the whole dataset (no
  pagination) while only ever holding a small window of rows in memory —
  see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how.
- Columns are tinted with alternating colors so it's easy to track a
  column visually while scrolling through a lot of rows.
- Starts in dark mode by default; System/Light/Dark are available under
  Settings > Appearance.
- Frameless window with a custom title bar, consistent across platforms.
  The File/Settings/Help menu bar lives in the title bar itself
  (VS Code-style) rather than a separate toolbar row; the open file's
  name shows in the title bar text.

## Quick start

Only prerequisite is Python 3.10+ on `PATH` (get it from
[python.org](https://www.python.org/downloads/) if you don't have it —
on Windows, check "Add python.exe to PATH" during install). Then, clone
or download-and-extract this repository and:

- **Windows:** double-click `run.bat` (or run it from a terminal/PowerShell).
- **Linux / macOS:** run `./run.sh` from a terminal.

First run creates a virtual environment and installs dependencies
(takes a minute); every run after that starts straight into the app.
Pass a file path through to open it directly:
`./run.sh path/to/data.h5` / `run.bat path/to/data.h5`.

The scripts are just a thin wrapper — nothing hidden — around:

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt   # venv\Scripts\pip.exe on Windows
venv/bin/python run.py                     # venv\Scripts\python.exe on Windows
```

**Linux troubleshooting:** if you see an error like *"could not load the
Qt platform plugin xcb"* mentioning `libxcb-cursor0`, install it (and Qt
will generally tell you exactly which package it's missing):

```bash
sudo apt install libxcb-cursor0     # Debian/Ubuntu/WSL
sudo dnf install xcb-util-cursor    # Fedora
```

This is normally already present on a full desktop Linux install (pulled
in by the desktop environment); it only tends to be missing on minimal/
headless installs or bare WSL distros without a desktop environment
installed.

## Download (prebuilt binaries)

If you'd rather not install Python, prebuilt Windows and Linux binaries
are published on the [Releases page](https://github.com/MartinMoan/yaht/releases)
for every tagged version. Each release has four assets to choose from:

|          | Recommended (onedir zip/tarball) | Single-file standalone |
|----------|-----------------------------------|-------------------------|
| Windows  | `YAHT-windows-x64.zip`            | `YAHT-windows-x64-standalone.exe` |
| Linux    | `YAHT-linux-x64.tar.gz`           | `YAHT-linux-x64-standalone.tar.gz` |

The onedir build starts faster and is less likely to trip antivirus
heuristics; the standalone build is a single file, handy for copying to
another machine (e.g. on a USB drive). See `packaging/README.md` for the
full tradeoffs.

These binaries are **unsigned**, so Windows SmartScreen will show a
"Windows protected your PC" warning on first run — expected for any
unsigned exe, not a sign of anything broken (click "More info" then "Run
anyway"). Code-signing isn't set up for this project (see
`packaging/README.md` for why); if that warning is a dealbreaker, the
"Quick start" above avoids it entirely — running your own freshly-built
code has nothing for SmartScreen to warn about.

macOS isn't built yet — Quick start (running from source) works there too,
though it isn't tested as regularly as Windows/Linux.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for running the test suite, and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the project layout and
the reasoning behind some of the less obvious implementation choices
(why Qt, why a frameless window, how large datasets are streamed into
the table view without loading them into memory).

## License

GPLv3 — see [LICENSE](LICENSE). You're free to use, modify, and
redistribute this software, including commercially, but any distributed
derivative work must also be open-sourced under GPLv3.
