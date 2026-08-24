# Packaging YAHT

Builds a standalone, installable-by-copy bundle for Windows and Linux via
[PyInstaller](https://pyinstaller.org/), chosen over Nuitka: this app's
own Python code isn't CPU-bound (h5py/numpy/Qt do the heavy lifting in
native code already), so Nuitka's actual compilation doesn't buy
meaningful speed here, and PyInstaller has by far the deeper track
record specifically with PySide6 + QtWebEngine, which is already this
codebase's most fragile dependency (see the deferred-import fallback in
`widgets/dataset_table.py`).

## Building locally

From the repository root, in a virtualenv with the app's normal
dependencies installed:

```bash
pip install -r requirements-build.txt
pyinstaller packaging/yaht.spec --noconfirm
```

This builds **two variants** from the same spec, so end users can pick
based on their situation:

- `dist/YAHT/` -- a folder ("onedir") containing `YAHT.exe`
  (Windows) / `YAHT` (Linux) plus everything it needs alongside it in
  `_internal/`. Starts up instantly and doesn't self-extract on every
  launch, and is far less likely to trip antivirus heuristics than a
  onefile exe. **Recommended default** -- distribute by zipping (Windows)
  or tar.gz-ing (Linux) the whole folder.
- `dist/YAHT-standalone.exe` (Windows) / `dist/YAHT-standalone`
  (Linux) -- a single self-contained file with everything embedded. Handy
  when there's only one file to copy around (e.g. onto a USB drive), at
  the cost of a few seconds' extra startup (it self-extracts to a temp
  directory on every launch) and a higher chance of antivirus/SmartScreen
  false positives, since that self-extraction pattern is also common in
  malware packaging.

Run either directly from `dist/` to test. See
`.github/workflows/build-release.yml`, which packages and publishes both
variants automatically for every tagged release.

## Linux system dependencies

QtWebEngine needs a handful of system Chromium runtime libraries that
PyInstaller can't bundle (they're OS packages, not Python packages) --
already documented in `requirements.txt` for running from source, and the
same libraries have to be present on the **build machine** too (PyInstaller
has to actually import `PySide6.QtWebEngineWidgets` while analyzing the
app) as well as on whatever Linux machine ultimately **runs** the built
bundle:

```bash
sudo apt-get install -y libnss3 libnspr4 libasound2t64 libxkbfile1 libxcb-cursor0
```

(Debian/Ubuntu package names; `libasound2t64` was `libasound2` before
Ubuntu 24.04's time_t transition -- use whichever your distro provides.)
Without these, the app itself still starts fine (the graph window fails
to import gracefully, per its own deferred-import handling), just with
graphing unavailable.

## Why the Windows exes aren't code-signed

The Windows exes (`YAHT.exe` inside the onedir bundle, and
`YAHT-standalone.exe`) are unsigned, which triggers a Windows SmartScreen
"Windows protected your PC" warning on first run -- expected for any
unsigned binary, not a sign of anything broken (click "More info" then
"Run anyway"). A paid code-signing certificate was considered and ruled
out (cost, for a hobby project); [SignPath Foundation](https://signpath.org/)'s
free signing for open-source projects was also evaluated and specifically
tried, but their application requires a "Reputation" case (existing
users, download stats, media coverage, etc.) that a brand-new project
genuinely doesn't have yet -- not a bar this project could honestly claim
to clear. Revisit this if the project gains real traction later.

In the meantime, the root README's "Quick start" (`run.sh` / `run.bat`)
is the answer for anyone put off by the SmartScreen warning: running
your own freshly-built code from source has nothing for SmartScreen to
warn about in the first place.

## What's *not* built here (possible future additions, not done now)

- A real Windows installer (Start Menu entry, uninstaller) via Inno Setup
  or NSIS -- currently just a portable zip. Straightforward to add later
  as another CI step once/if wanted.
- A Linux AppImage/.deb/.rpm -- currently just a portable tar.gz. Same
  story: doable later, deliberately not built now to keep this first pass
  simple and robust.
- A custom app icon -- there's no `.ico`/`.png` app icon in this repo yet
  (the app draws its *in-window* icons on the fly via Pillow, see
  `icons.py`, but never sets a taskbar/window icon), so builds use
  PyInstaller's default. Add `icon=str(repo_root / "packaging" / "app.ico")`
  (Windows) to the `EXE(...)` call in `yaht.spec` once one exists.
- macOS -- explicitly out of scope for now per the request that set this
  up.
