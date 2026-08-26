"""Main application window: wires the hierarchy tree, dataset table and
group overview panel together around one or more open HDF5 files (e.g.
every .h5 file found in a directory) -- see open_paths.

The window is frameless (``Qt.FramelessWindowHint``) with a hand-drawn
title bar (``widgets/title_bar.py``), because the native window frame is
drawn by the OS/window manager and looks different (and, on WSLg,
noticeably dated) per platform -- the opposite of what this rewrite is
for. Move uses Qt's native, OS-assisted ``startSystemMove``, not
hand-rolled geometry math. Maximize is the one exception: Qt's own
``showMaximized()`` on a frameless X11 window doesn't reliably know there
are no decorations to account for, and ends up positioning the window
offset from the screen edge -- so maximize/restore is done manually here
by setting geometry to the screen's available rect instead.

Edge-resize and manual maximize/restore are shared with the graph window
via ``FramelessWindowMixin`` (``widgets/frameless.py``) -- see that
module's docstring for the full story, including why the resize event
filter must be installed per-widget on this window's own descendants
rather than QApplication-wide (it broke QWebEngineView).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLayout,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from constants import APP_NAME, H5_SUFFIXES
from core.file_loader import MultiFileLoader
from core.h5_model import H5Model, H5ModelError, NodeInfo
from theme import Palette, ThemeManager
from widgets.dataset_tabs import DatasetTabsView
from widgets.file_open_dialog import FileOpenDialog
from widgets.frameless import FramelessWindowMixin
from widgets.hierarchy_tree import HierarchyTree
from widgets.status_bar import StatusBar
from widgets.title_bar import BAR_HEIGHT, TitleBar

_DEFAULT_W, _DEFAULT_H = 1320, 840
_MIN_W, _MIN_H = 860, 560


class App(FramelessWindowMixin, QWidget):
    def __init__(self, initial_paths: Optional[list[str]] = None):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        # One entry per currently-open file -- e.g. every .h5 file in a
        # directory passed on the command line or picked via "Open"
        # without selecting one specific file (see open_paths).
        self.models: list[H5Model] = []
        # Opening several files happens on a background thread pool (see
        # core/file_loader.py) so the GUI thread is never blocked waiting
        # for the slowest one -- this timer polls for files as they
        # finish, in whatever order that happens to be. None when nothing
        # is currently loading.
        self._loader: Optional[MultiFileLoader] = None
        self._load_poll_timer = QTimer(self)
        self._load_poll_timer.setInterval(30)
        self._load_poll_timer.timeout.connect(self._poll_loader)
        # A load superseded by a newer open_paths() call before it
        # finished -- its threads can't be interrupted mid-open, so
        # models it still produces are just closed as they arrive
        # instead of being shown (see _cancel_loading/_poll_loader).
        self._orphaned_loaders: list[MultiFileLoader] = []
        self._pending_errors: list[str] = []
        self._first_root_selected = False
        self.theme = ThemeManager(QApplication.instance())
        self.theme.set_mode("dark")

        self._outer_layout = QVBoxLayout(self)
        outer = self._outer_layout
        # Flush with the window edges (VS Code-style) -- no reserved
        # border. See the module docstring for how edge-resize works
        # without one.
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # Qt's default top-level-layout behavior propagates this layout's
        # computed size hints up to the *window's* own min/max size
        # whenever any descendant's geometry changes -- e.g. a splitter
        # drag. We already manage this window's geometry entirely by hand
        # (resize/setGeometry/startSystemMove/startSystemResize, all the
        # way up in _toggle_maximize et al.), so Qt's layout engine also
        # trying to influence window size on top of that is exactly the
        # kind of conflict that could make the window jump during an
        # unrelated internal layout change. Opt out of it entirely.
        outer.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)

        self.title_bar = TitleBar(
            self.theme, APP_NAME,
            on_open_file=self._open_file_dialog,
            on_set_appearance=self.theme.set_mode,
            on_minimize=self.showMinimized,
            on_toggle_maximize=self._toggle_maximize,
            on_close=self.close,
        )
        outer.addWidget(self.title_bar)

        self._build_body(outer)

        self.status_bar = StatusBar(self.theme)
        outer.addWidget(self.status_bar)
        self.dataset_tabs.context_changed.connect(self.status_bar.set_context)
        self.dataset_tabs.error_message.connect(lambda msg: self.status_bar.set_message(msg, is_error=True))

        # A resize cursor set on this widget (see mouseMoveEvent below,
        # only meant for the few pixels of bare margin around the window
        # edge) is otherwise *inherited* by every descendant that doesn't
        # set its own cursor -- which is everything here. Trying to time a
        # reset via leaveEvent wasn't reliable through several layers of
        # nested widgets; explicitly giving each direct child its own
        # ArrowCursor breaks the inheritance chain at the source instead,
        # so nothing below this level can ever show the wrong cursor
        # regardless of what App.cursor() currently is.
        for child in (self.title_bar, self.splitter, self.status_bar):
            child.setCursor(Qt.CursorShape.ArrowCursor)

        self._init_frameless(BAR_HEIGHT)

        self._center_on_screen()
        self.theme.register(self._apply_palette)

        if initial_paths:
            self.open_paths(initial_paths)

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.center().x() - self.width() // 2, geo.center().y() - self.height() // 2)

    # -- layout ------------------------------------------------------

    def _build_body(self, outer: QVBoxLayout) -> None:
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(6)

        self.tree = HierarchyTree(
            self.theme, on_select=self._on_node_selected, on_activate=self._on_node_activated
        )
        self.splitter.addWidget(self.tree)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.dataset_tabs = DatasetTabsView(
            self.theme,
            on_child_activate=self._activate_path,
            on_child_double_activate=self._activate_path_permanent,
        )
        right_layout.addWidget(self.dataset_tabs)
        self.splitter.addWidget(right)

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([280, _DEFAULT_W - 280])

        outer.addWidget(self.splitter, 1)

    # -- file lifecycle ------------------------------------------------

    def _open_file_dialog(self) -> None:
        start_dir = str(Path(self.models[-1].path).parent) if self.models else str(Path.home())
        dialog = FileOpenDialog(self.theme, start_dir=start_dir, parent=self)
        paths = dialog.get_paths()
        if paths:
            self.open_paths(paths)

    def open_file(self, path: str) -> None:
        self.open_paths([path])

    def open_paths(self, paths: list[str]) -> None:
        """Opens ``paths`` as a fresh session, replacing whatever's
        currently open -- each entry is either an .h5 file, used as-is,
        or a directory, expanded to every .h5 file directly inside it
        (see the file-open dialog's "no file selected" case, and the CLI
        entry point, for the two ways a directory ends up here).
        De-duplicates by resolved path, so e.g. ``yaht a.h5 .`` (a.h5
        both named explicitly and found again via the directory scan)
        doesn't open it twice.

        The actual h5py.File opens happen on a background thread pool,
        not here -- see core/file_loader.py's docstring for why opening
        several files sequentially on the GUI thread is what made this
        feel slow in the first place. The sidebar fills in progressively
        as each one finishes; see _poll_loader."""
        resolved = self._resolve_paths(paths)
        if not resolved:
            return

        self._cancel_loading()
        self.dataset_tabs.clear_all()
        for old_model in self.models:
            old_model.close()
        self.models = []
        self._pending_errors = []
        self._first_root_selected = False

        self.tree.begin_loading([Path(p).name for p in resolved])
        self.tree.tree.setFocus()
        noun = "file" if len(resolved) == 1 else "files"
        self.status_bar.set_path(None)
        self.status_bar.set_message(f"Opening {len(resolved)} {noun}...")

        self._loader = MultiFileLoader(resolved)
        self._load_poll_timer.start()

    def _resolve_paths(self, paths: list[str]) -> list[str]:
        resolved: list[str] = []
        seen: set[str] = set()

        def add(p: Path) -> None:
            key = str(p.resolve()) if p.exists() else str(p)
            if key not in seen:
                seen.add(key)
                resolved.append(str(p))

        for raw in paths:
            candidate = Path(raw).expanduser()
            if candidate.is_dir():
                found = sorted(
                    (f for f in candidate.iterdir() if f.is_file() and f.suffix.lower() in H5_SUFFIXES),
                    key=lambda f: f.name.lower(),
                )
                if not found:
                    self.status_bar.set_message(f"No .h5 files found in {candidate}", is_error=True)
                    continue
                for f in found:
                    add(f)
            else:
                add(candidate)
        return resolved

    def _cancel_loading(self) -> None:
        # Can't interrupt a thread mid-open, so a load already running
        # when a new open_paths() call comes in is left to finish on its
        # own -- just orphaned, so _poll_loader closes whatever it
        # produces instead of adding it to the (by-then-replaced) sidebar.
        if self._loader is not None and not self._loader.is_done():
            self._orphaned_loaders.append(self._loader)
        self._loader = None

    def _poll_loader(self) -> None:
        for orphan in list(self._orphaned_loaders):
            for result in orphan.poll_updates():
                if result.model is not None:
                    result.model.close()
            if orphan.is_done():
                self._orphaned_loaders.remove(orphan)

        if self._loader is None:
            if not self._orphaned_loaders:
                self._load_poll_timer.stop()
            return

        for result in self._loader.poll_updates():
            if result.model is not None:
                self.models.append(result.model)
                root_item = self.tree.resolve_root(result.index, result.model)
                if not self._first_root_selected:
                    self.tree.expand_and_select(root_item)
                    self._first_root_selected = True
            else:
                self._pending_errors.append(f"{Path(result.path).name}: {result.error}")
                self.tree.resolve_error(result.index, result.error or "")

        if self._loader.is_done():
            self._loader = None
            n = len(self.models)
            if n == 1:
                self.status_bar.set_path(self.models[0].path)
                self.status_bar.set_message("File loaded")
            elif n > 1:
                self.status_bar.set_message(f"Loaded {n} files")
            if self._pending_errors:
                self.status_bar.set_message(f"Some files failed to open: {'; '.join(self._pending_errors)}", is_error=True)
            elif n == 0:
                self.status_bar.set_message("Could not open file(s)", is_error=True)
            if not self._orphaned_loaders:
                self._load_poll_timer.stop()

    def _on_node_selected(self, model: H5Model, node: NodeInfo) -> None:
        self._open_node(model, node, permanent=False)

    def _on_node_activated(self, model: H5Model, node: NodeInfo) -> None:
        # Tree double-click -- see HierarchyTree's on_activate. Groups
        # still also expand/collapse on double-click via Qt's own default
        # QTreeView behavior; this additionally pins the group's own tab,
        # same as it does for datasets.
        self._open_node(model, node, permanent=True)

    def _open_node(self, model: H5Model, node: NodeInfo, permanent: bool) -> None:
        try:
            self.dataset_tabs.open_node(model, node, permanent=permanent)
        except H5ModelError as exc:
            self.status_bar.set_message(str(exc), is_error=True)

    def _activate_path(self, model: H5Model, path: str) -> None:
        self.tree.select_path(model, path)

    def _activate_path_permanent(self, model: H5Model, path: str) -> None:
        # Group panel's child-row double-click -- mirrors
        # _on_node_activated reached this way instead of via the tree
        # directly. select_path already fires _on_node_selected (a
        # preview open) through the tree's own selectionChanged; this
        # then pins/promotes that same node to a permanent tab, the same
        # order double-clicking a tree row happens in.
        self.tree.select_path(model, path)
        node = model.node_info(path)
        self._open_node(model, node, permanent=True)

    def closeEvent(self, event) -> None:
        self._teardown_frameless()
        self._load_poll_timer.stop()
        self.dataset_tabs.clear_all()
        for model in self.models:
            model.close()
        super().closeEvent(event)

    # -- window chrome -----------------------------------------------------
    # Maximize/restore and edge-resize live in FramelessWindowMixin, shared
    # with the graph window -- see widgets/frameless.py.

    def _on_maximize_changed(self, maximized: bool) -> None:
        self.title_bar.set_maximized(maximized)

    # -- theming ---------------------------------------------------------

    def _apply_palette(self, palette: Palette) -> None:
        # header_bg, not window_bg: there's no reserved margin any more
        # for this to show through, but it's still App's own background
        # underneath every child widget, so keeping it matched to the
        # title/status bar avoids even a one-frame flash of a mismatched
        # color during resize/relayout.
        self.setStyleSheet(
            f"""
            App {{ background-color: {palette.header_bg}; }}
            QWidget {{ color: {palette.text}; }}
            QSplitter::handle {{
                background-color: {palette.splitter};
            }}
            QSplitter::handle:hover {{
                background-color: {palette.accent};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {palette.accent};
                min-height: 24px;
                border-radius: 3px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                border: none;
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {palette.accent};
                min-width: 24px;
                border-radius: 3px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                border: none;
                background: none;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}
            """
        )


def main(initial_paths: Optional[list[str]] = None) -> None:
    # Required by Qt WebEngine (see widgets/graph_window.py) *before* the
    # QApplication exists -- without it, QWebEngineView's separate GPU/
    # renderer processes don't share GL contexts with the main process,
    # which showed up here as sporadic Chromium GPU-command-buffer errors
    # and crashes around graph windows. Harmless no-op for the rest of the
    # app if WebEngine's system dependencies aren't installed.
    if QApplication.instance() is None:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([])
    window = App(initial_paths)
    window.show()
    app.exec()
