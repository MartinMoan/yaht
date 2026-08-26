# Architecture notes

Implementation background for anyone modifying the codebase — not needed
just to use the app. See the root `README.md` for that.

## Why Qt, and why frameless

This app used to be Tkinter/CustomTkinter. It moved to Qt because the
goal is for it to look and behave *identically* on native Windows, native
Linux, and WSL — and Tk fundamentally can't do that: `ttk` widgets
delegate to whatever native theming engine the OS provides, so the same
app looks different (and, on a minimal WSLg setup, noticeably dated) on
each platform. Qt is forced into its "Fusion" style here (see
`theme.py`), which Qt draws itself, pixel for pixel the same regardless
of OS — the same idea VS Code uses (a bundled rendering engine instead of
native widgets), just via Qt's own widget set instead of a browser
engine, which let almost the entire Python/h5py backend from the Tk
version carry over unchanged (`core/h5_model.py`, `core/dataset_source.py`
— the lazy navigation and the threaded chunked dataset loader).

The window itself is frameless (`Qt.FramelessWindowHint`) with a
hand-drawn title bar (`widgets/title_bar.py`), because the native window
frame is drawn by the OS/window manager and no toolkit can restyle that.
Move/resize use Qt's native, OS-assisted window operations
(`startSystemMove`/`startSystemResize`), not hand-rolled geometry math —
this matters because an earlier Tk prototype hand-rolled frameless
support via `overrideredirect`, which turned out to reliably **crash the
X connection** under WSLg the moment `iconify()` was called on a window
that had ever had its frame toggled off. Qt's frameless support is a
proper, first-class, widely-shipped window flag rather than a raw X11
hack, and minimize (`showMinimized()`) was verified safe in the exact
same environment that broke under Tk. Maximize is the one place Qt's own
`showMaximized()` wasn't trustworthy either: on a frameless X11 window it
doesn't reliably know there are no decorations to account for and can
leave the window offset from the screen edge, so maximize/restore sets
geometry to the screen's available rect directly instead (`app.py`,
`_toggle_maximize`).

"Open File…" is a custom `QDialog` (`widgets/file_open_dialog.py`)
rather than Qt's stock `QFileDialog` — the stock dialog only inherits our
`QApplication`-wide palette (base colors), not the app's QSS styling
(rounded rows, accent icons, hover states), since stylesheets don't
cascade across separate top-level windows; left alone it looks like a
plain, dated Fusion dialog. It's still a real `QDialog` though (properly
parented to the main window), so it doesn't have the stacking/focus bugs
an unparented Tk `Toplevel` had. Path entry uses Qt's own
`QCompleter`+`QFileSystemModel` for native type-ahead completion.

## How large datasets are handled

Opening a dataset never reads it into memory. Instead:

1. The dataset's shape/dtype is turned into a flat column layout (an N-D
   or compound dataset gets its trailing dimensions and/or field names
   flattened into columns; extremely wide datasets are capped at 256
   columns with a warning banner rather than freezing the UI).
2. `DatasetTableModel` (a `QAbstractTableModel`) reports the dataset's
   real row count, but Qt's `QTableView` only ever calls `data()` for
   cells that are actually on screen — virtualization is built into Qt's
   model/view framework, not something hand-rolled here.
3. When `data()` is asked for a row whose block hasn't loaded yet, it
   returns a `···` placeholder immediately and kicks off a background
   load via `DatasetSource`, which reads fixed-size blocks (200 rows by
   default) from disk on a single worker thread — h5py's slicing already
   only touches the requested region of the file — and caches recently
   used blocks (LRU-ish eviction) so scrolling back is instant.
4. A small `QTimer` polls the source and emits `dataChanged` for whatever
   finished loading since the last tick, so the view redraws itself
   automatically as data arrives.

This is what lets the view scroll smoothly and continuously from row 0 to
row N even when N is very large, without ever pausing to "page" or
loading more than a sliver of the dataset into memory at once. A "Row #"
jump box plus Top/End buttons are provided for quickly navigating within
huge datasets without physically scrolling the whole way. (One real limit
worth knowing: Qt's row counts are 32-bit, so a single dataset topping
roughly 2.1 billion rows would need a different approach — not something
either the old Tk version or this one handles.)

## How opening several files at once is parallelized

Opening a directory can mean opening dozens of files at once, and doing
that one after another on the GUI thread -- h5py.File(...) plus reading
the root group's immediate children for the sidebar, for every file,
before any of it is shown -- is what made that feel slow, especially
when most of the time is I/O *wait* (a slow disk, a network drive, or a
WSL path crossing the 9p boundary into Windows) rather than actual CPU
work, since none of those waits overlap.

`core/file_loader.py`'s `MultiFileLoader` runs each file's open on its
own thread from a small pool (capped at 8 workers -- see its docstring
for why more threads than that wouldn't help: HDF5 serializes actual
library calls behind its own global lock regardless of thread count, so
this is about overlapping I/O wait, not CPU parallelism). Results come
back through a queue, labeled with their original index, in whatever
order they actually finish -- not necessarily the order the files were
given in.

`App` polls that queue on a `QTimer` (same "background thread + queue +
UI-thread poll" shape as `DatasetSource`, just for opening files instead
of reading rows) and, as each result arrives, turns the corresponding
placeholder row in `HierarchyTree` (reserved up front by `begin_loading`,
in the *original*, stable order -- so the sidebar doesn't reshuffle as
files race to finish) into a real root via `resolve_root`, or marks it
failed via `resolve_error`. Whichever file happens to finish loading
first is auto-expanded and selected, so there's something to look at (and
navigate) immediately instead of waiting for every file, including
however many are still mid-flight.

Root items are also lazy now, the same dummy-child trick already used
for every other group: `resolve_root` only needs the cheap root-level
child *count* (for the expand arrow), not a full immediate-children
listing with per-child shape/dtype -- that only happens once a root is
actually expanded, which by default is just the one auto-selected file,
not all N.

## Project layout

```
src/
  run.py                        entry point: python src/run.py [file.h5]
  app.py                        main window + frameless window chrome
  theme.py                      Fusion style, QPalette, light/dark detection
  constants.py                  sizing + column color palette
  icons.py                      Pillow-drawn icons -> QPixmap/QIcon
  core/
    h5_model.py                 lazy h5py navigation, column-layout logic
    dataset_source.py           threaded, cached, chunked row reader
    file_loader.py               thread-pooled opener for several files at once
  widgets/
    title_bar.py                 custom frameless-window title bar
    file_open_dialog.py           custom-styled "Open File" QDialog
    hierarchy_tree.py           left-pane explorer (QTreeView)
    dataset_table.py            virtualized table (QTableView + model)
    group_panel.py              overview shown for groups / file root
    status_bar.py                bottom status strip
scripts/
  run.sh / run.bat              launch from source (sets up a venv first)
  install.sh / install.ps1 /    build from source and install locally
    install.bat
tests/                          pytest suite for core/ (no GUI)
```
