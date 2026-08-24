# Packaging YAHT

Builds a standalone, installable-by-copy bundle for Windows and Linux via
[PyInstaller](https://pyinstaller.org/). See the repository root README (or
ask the assistant that set this up) for the full evaluation of *why*
PyInstaller over Nuitka -- short version: this app's own Python code isn't
CPU-bound (h5py/numpy/Qt do the heavy lifting in native code already), so
Nuitka's actual compilation doesn't buy meaningful speed here, and
PyInstaller has by far the deeper track record specifically with PySide6 +
QtWebEngine, which is already this codebase's most fragile dependency (see
the deferred-import fallback in `widgets/dataset_table.py`).

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

## Code signing

The Windows exes (`YAHT.exe` inside the onedir bundle, and
`YAHT-standalone.exe`) are unsigned by default, which triggers a
Windows SmartScreen "Windows protected your PC" warning on first run for
every user -- expected for any unsigned binary, not a sign of anything
actually being broken. `build-release.yml`'s `build-windows` job has a
signing step built in via [SignPath](https://signpath.io/), which
offers free code signing for open-source projects through the
[SignPath Foundation](https://signpath.org/). Only the two YAHT exes
get signed -- not the bundled third-party Qt/Python DLLs, which don't
need it and aren't ours to sign.

Signing is entirely opt-in and fails safe: every signing step in the
workflow is gated on the `SIGNPATH_API_TOKEN` repo secret being set, so
an unconfigured repo just builds unsigned exes exactly as before, no
workflow failures. To turn it on:

1. **Make the repo public** (Settings > General > Danger Zone > Change
   visibility) -- SignPath Foundation signs open-source projects, which
   in practice means a public repo under an OSS license (this repo uses
   GPLv3, see `../LICENSE`).
2. **Apply to SignPath Foundation**: <https://signpath.org/apply>. Free,
   but manual review -- read their terms first. There's no fixed SLA on
   turnaround, so budget some slack before your first real release if
   you want it signed.
3. **Once approved**, in the SignPath dashboard:
   - Note your **organization ID**.
   - Create a **project** (a slug, e.g. `yaht`).
   - Create a **signing policy** (a slug, e.g. `release-signing`) --
     this is where SignPath's own review/approval rules for release
     builds live.
   - Generate an **API token** for a user with submitter permissions.
4. **Install the SignPath GitHub App** on this repo:
   <https://github.com/apps/signpath>. This is how SignPath verifies a
   signing request actually came from a build of your repo, not from
   someone who merely obtained your API token.
5. **Add the API token as a repo secret**: Settings > Secrets and
   variables > Actions > New repository secret, named
   `SIGNPATH_API_TOKEN`.
6. **Fill in the three placeholders** at the top of
   `.github/workflows/build-release.yml` (`SIGNPATH_ORGANIZATION_ID`,
   `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_SIGNING_POLICY_SLUG`) with the
   values from step 3. These aren't secret, so they're plain workflow
   `env:` vars, not repo secrets.
7. Trigger a build (`workflow_dispatch` or a tag push) and confirm the
   "Sign onedir exe" / "Sign standalone exe" steps actually ran instead
   of being skipped.

None of steps 1-4 can be done by an assistant on your behalf -- they
require your own GitHub/SignPath accounts and identity. Only step 6 is a
repo file edit.

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
