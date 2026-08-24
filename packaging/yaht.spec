# PyInstaller spec for YAHT (Yet Another Hdf5 Tool).
#
# Build (from the repository root, so the relative paths below resolve):
#   pyinstaller packaging/yaht.spec --noconfirm
#
# Produces two builds from the same Analysis, so users can pick based on
# their situation:
#
#   dist/YAHT/                 "onedir" -- a folder containing the
#                               executable plus its dependencies.
#                               Starts up instantly, doesn't
#                               self-extract on every launch, and is
#                               far less likely to be flagged by
#                               antivirus heuristics. Distribute by
#                               zipping/tarring the whole folder (see
#                               .github/workflows/build-release.yml).
#                               This is the recommended default.
#
#   dist/YAHT-standalone(.exe) "onefile" -- a single self-contained
#                               executable. Convenient to copy to
#                               another machine (e.g. on a USB drive)
#                               since there's only one file, at the
#                               cost of a few seconds' extra startup
#                               time (it self-extracts to a temp
#                               directory on every launch) and a
#                               somewhat higher chance of antivirus/
#                               SmartScreen false positives, since
#                               self-extracting single-exe blobs are a
#                               common malware packaging pattern.
from pathlib import Path

# SPECPATH is injected by PyInstaller into this file's exec globals --
# it's this .spec file's own directory (packaging/), so repo_root
# resolves correctly regardless of the caller's current working directory.
repo_root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(repo_root / "run.py")],
    pathex=[str(repo_root / "src")],
    binaries=[],
    datas=[
        # The vendored plotly.min.js (see widgets/graph_window.py) --
        # ASSETS_DIR there is frozen-build-aware (checks sys.frozen /
        # sys._MEIPASS) specifically so this path lines up at runtime.
        (str(repo_root / "src" / "assets"), "assets"),
    ],
    hiddenimports=[
        # QtWebEngineWidgets is imported lazily/defensively at runtime
        # (see widgets/dataset_table.py's _on_make_graph) specifically so
        # the app still starts without it -- PyInstaller's static import
        # analysis doesn't see that deferred import at all, so it has to
        # be listed explicitly or the graph window silently never gets
        # bundled.
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebChannel",
        "PySide6.QtPrintSupport",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

# onedir target -- exe here is just the launcher stub; COLLECT below
# gathers it plus a.binaries/a.datas into dist/YAHT/.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YAHT",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # windowed GUI app -- no terminal window alongside it
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="YAHT",
)

# onefile target -- binaries/datas are embedded directly in the exe
# (exclude_binaries=False, no COLLECT), so this is a second, independent
# build product, not a repackaging of the onedir output above. Named
# differently from "YAHT" so the two don't collide on disk (on Linux,
# a file and a directory can't share a name).
exe_onefile = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name="YAHT-standalone",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    runtime_tmpdir=None,  # default: self-extracts under the OS temp dir
)
