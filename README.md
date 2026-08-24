# YAHT

**Y**et **A**nother **H**df5 **T**ool — a modern, cross-platform desktop
viewer for HDF5 (`.h5`) files, built with
[PySide6 (Qt for Python)](https://doc.qt.io/qtforpython-6/) and
[h5py](https://www.h5py.org/).

<!-- TODO: replace with a real screenshot at docs/screenshot.png -->
![YAHT screenshot](docs/screenshot.png)

## Quick start

### Prerequisites

- Python 3.10+ on `PATH` — [python.org](https://www.python.org/downloads/)
  (check "Add python.exe to PATH" during install on Windows).
- This repository, cloned or downloaded and extracted.

### Windows

Double-click `scripts/run.bat`.

### Linux

```bash
./scripts/run.sh
```

If this fails with a *"could not load the Qt platform plugin xcb"*
error mentioning `libxcb-cursor0`, install it:
`sudo apt install libxcb-cursor0` (Debian/Ubuntu/WSL) or
`sudo dnf install xcb-util-cursor` (Fedora) — normally only missing on
minimal/headless installs.

### macOS

```bash
./scripts/run.sh
```

Not tested as regularly as Windows/Linux.

---

First run installs dependencies into a local `.venv/` (~1 minute); every
run after that starts straight into the app. Pass a file path to open it
directly: `./scripts/run.sh data.h5` / `scripts\run.bat data.h5`.

<details>
<summary>What the scripts actually do</summary>

Run from the repository root (the scripts `cd` there automatically):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # .venv\Scripts\pip.exe on Windows
.venv/bin/python src/run.py                 # .venv\Scripts\python.exe on Windows
```

</details>

## Install (build from source)

Builds a real standalone copy with PyInstaller and installs it for your
user account — no admin/sudo rights needed. Detects an existing install
first and asks before touching it (uninstall-and-continue, or abort).

- **Windows:** double-click `scripts/install.bat`.
- **Linux:** run `./scripts/install.sh` in a terminal.

| OS | Installed to | Shortcut |
|----|--------------|----------|
| Windows | `%LOCALAPPDATA%\Programs\YAHT` | Start Menu entry ("YAHT" and "Uninstall YAHT") |
| Linux | `~/.local/share/yaht` | Application-menu entry, plus a `yaht` command on `~/.local/bin` |

To uninstall later without re-running the installer: use the "Uninstall
YAHT" Start Menu shortcut (Windows), or run
`~/.local/share/yaht/uninstall.sh` (Linux) — both work standalone,
without needing this repository around.

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

macOS isn't built as a prebuilt binary — see "Quick start" above instead.

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
