"""Left-hand explorer pane: a lazily-populated group/dataset tree, similar
in spirit to VS Code's file explorer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTreeView, QVBoxLayout, QWidget

import constants
import icons
from core.h5_model import DATASET, GROUP, H5Model, NodeInfo
from format_utils import format_size
from theme import Palette, ThemeManager

ICON_SIZE = 15
NODE_ROLE = Qt.ItemDataRole.UserRole + 1
DUMMY_ROLE = Qt.ItemDataRole.UserRole + 2
# Which H5Model a given item belongs to -- needed once more than one
# file can be open at once (each gets its own root item), since NodeInfo
# itself only carries an in-file path, not which file it's from.
MODEL_ROLE = Qt.ItemDataRole.UserRole + 3


def _shape_summary(node: NodeInfo) -> str:
    """Used by the group overview panel and the file-open dialog -- not by
    this tree itself. A previous version of this tree also showed this as
    a second column next to each row, but sizing that column to fit its
    widest value (a dataset's full "shape · dtype" string) padded out
    every row to match, including plain group rows that only needed "N
    items" -- compounding with indentation into a sidebar that ballooned
    on deep hierarchies for no real benefit, since this info is already
    shown when a dataset is actually selected."""
    if node.kind == DATASET:
        shape = "scalar" if node.shape == () else "×".join(str(d) for d in node.shape)
        return f"{shape}  {node.dtype}"
    if node.n_children == 1:
        return "1 item"
    return f"{node.n_children} items"


class HierarchyTree(QWidget):
    def __init__(
        self,
        theme: ThemeManager,
        on_select: Callable[[H5Model, NodeInfo], None],
        on_activate: Optional[Callable[[H5Model, NodeInfo], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._on_select = on_select
        # Fired on double-click, in addition to (after) the selectionChanged
        # -> on_select call the double-click's first press already
        # triggers -- lets App distinguish "open as preview" (single
        # click/keyboard nav, on_select) from "open pinned/permanent"
        # (double-click, on_activate), VS Code-editor-tab style. Optional
        # only so any other future embedder of this tree isn't forced to
        # care about that distinction.
        self._on_activate = on_activate
        # Keyed by (model, in-file path) -- a bare path isn't unique once
        # more than one file can be open, since two different files can
        # both have e.g. "/data".
        self._items: dict[tuple[H5Model, str], QStandardItem] = {}
        # Placeholder root rows reserved by begin_loading, index-aligned
        # with the paths a load was started with -- see resolve_root/
        # resolve_error, which turn each into a real (or failed) root as
        # its file finishes opening in the background. _loading_names
        # keeps the plain filename around separately from the item's own
        # (mutable, progress-suffixed) text, and _failed_indices tells
        # update_loading_progress to stop touching a row once
        # resolve_error has claimed it.
        self._loading_items: list[QStandardItem] = []
        self._loading_names: list[str] = []
        self._failed_indices: set[int] = set()
        self._palette: Palette = theme.palette
        # Otherwise transparent, so the top/left layout margin below would
        # expose App's own (darker) background rather than the tree's own
        # panel color -- reading as the whole pane having shifted position
        # rather than just the tree content getting a bit of breathing
        # room within it.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 10, 0, 4)

        self.model = QStandardItemModel()

        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(18)
        self.tree.setAnimated(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setFrameShape(QTreeView.Shape.NoFrame)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # ResizeToContents (not Stretch): names should always be shown in
        # full, never truncated to fit the pane -- the sidebar grows to
        # match instead (see _apply_min_width below).
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.tree)

        self.tree.expanded.connect(self._on_expanded)
        self.tree.collapsed.connect(self._on_collapsed)
        self.tree.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.tree.doubleClicked.connect(self._on_double_clicked)

        theme.register(self._apply_palette)

    # -- public API ------------------------------------------------------

    def begin_loading(self, filenames: list[str]) -> None:
        """Reserves one placeholder root row per file, in this exact
        order, before any of them have actually finished opening --
        opening several files happens on background threads (see
        core/file_loader.py) so the sidebar doesn't have to sit empty (or
        fill in in whatever order the threads happen to finish) while
        that's in progress. Each placeholder is later turned into a real
        root by resolve_root, or marked failed by resolve_error, by
        index -- see App._poll_loader, which also drives
        update_loading_progress for whichever ones are still pending."""
        self.clear()
        for name in filenames:
            item = QStandardItem(name)
            item.setEditable(False)
            item.setEnabled(False)  # not selectable until resolved (or permanently, if it errors)
            item.setIcon(icons.icon(GROUP, self._palette.subtext, ICON_SIZE))
            self.model.appendRow(item)
            self._loading_items.append(item)
            self._loading_names.append(name)
        self._apply_min_width()

    def update_loading_progress(self, index: int, bytes_read: int, total_size: int) -> None:
        """Shows live "N% read" next to a still-loading placeholder's
        filename. A no-op once that row has actually resolved or failed
        (resolve_root/resolve_error take over its text at that point)."""
        if index in self._failed_indices:
            return
        item = self._loading_items[index]
        if item.data(MODEL_ROLE) is not None:
            return
        percent = int(bytes_read / total_size * 100) if total_size else 0
        item.setText(f"{self._loading_names[index]}   {min(percent, 99)}%")

    def resolve_root(self, index: int, model: H5Model, root_info: NodeInfo, size: int) -> QStandardItem:
        """Turns the placeholder at ``index`` (see begin_loading) into a
        real, expandable root for ``model``, lazily -- same dummy-child
        trick as any other group, so opening e.g. 20 files up front only
        means 20 fast opens, not 20 full immediate-children listings;
        only the file(s) actually expanded (at minimum, whichever one is
        shown by default -- see App._poll_loader) pay for that.

        ``root_info`` and ``size`` come pre-computed from the background
        loader (core/file_loader.py) rather than being read here -- this
        method touches no h5py state at all, just Qt objects, so it's
        safe (and fast) to call straight from the GUI thread."""
        item = self._loading_items[index]
        item.setEnabled(True)
        item.setData(root_info, NODE_ROLE)
        item.setData(model, MODEL_ROLE)
        item.setIcon(icons.icon(root_info.kind, self._icon_color(root_info.kind), ICON_SIZE))
        item.setText(f"{self._loading_names[index]}   {format_size(size)}")
        self._items[(model, "/")] = item
        if (root_info.n_children or 0) > 0:
            dummy = QStandardItem("")
            dummy.setEditable(False)
            dummy.setData(True, DUMMY_ROLE)
            item.appendRow([dummy])
        self._apply_min_width()
        return item

    def resolve_error(self, index: int, message: str) -> None:
        """Marks the placeholder at ``index`` as failed to open -- left
        in the sidebar (not removed) so it's still obvious which file
        that was, distinct from one that's still loading."""
        self._failed_indices.add(index)
        item = self._loading_items[index]
        item.setText(f"{self._loading_names[index]}  — failed to open")
        item.setToolTip(message)
        warn_color = constants.WARN_COLOR_DARK if self._palette.dark else constants.WARN_COLOR_LIGHT
        item.setIcon(icons.icon(GROUP, warn_color, ICON_SIZE))

    def expand_and_select(self, item: QStandardItem) -> None:
        """Reveals and selects a just-resolved root -- used once, for
        whichever file finishes loading first (not necessarily the first
        one listed), so there's something to look at immediately instead
        of the sidebar sitting there fully loaded but nothing shown."""
        self.tree.expand(item.index())
        self.tree.setCurrentIndex(item.index())  # triggers _on_selection_changed

    def clear(self) -> None:
        self.model.removeRows(0, self.model.rowCount())
        self._items.clear()
        self._loading_items = []
        self._loading_names = []
        self._failed_indices = set()

    def select_path(self, model: H5Model, path: str) -> None:
        """Programmatically reveal and select ``path`` within ``model``,
        lazily expanding any ancestor groups that haven't been populated
        yet. Used when a child row is clicked in the group overview
        panel."""
        if (model, "/") not in self._items:
            return

        parts = [p for p in path.split("/") if p]
        current = "/"
        for i in range(len(parts) + 1):
            if i > 0:
                current = "/" + "/".join(parts[:i])
            item = self._items.get((model, current))
            if item is None:
                return
            if item.rowCount() == 1 and item.child(0).data(DUMMY_ROLE):
                item.removeRow(0)
                self._populate_children(model, current, item)

        item = self._items.get((model, path))
        if item is None:
            return
        index = item.index()
        parent = index.parent()
        while parent.isValid():
            self.tree.expand(parent)
            parent = parent.parent()
        self.tree.setCurrentIndex(index)  # triggers _on_selection_changed
        self.tree.scrollTo(index)
        self._apply_min_width()

    # -- internals ---------------------------------------------------------

    def _icon_color(self, kind: str) -> str:
        return self._palette.subtext if kind == GROUP else self._palette.accent

    def _make_name_item(self, node: NodeInfo, label: str) -> QStandardItem:
        item = QStandardItem(label)
        item.setEditable(False)
        item.setData(node, NODE_ROLE)
        item.setIcon(icons.icon(node.kind, self._icon_color(node.kind), ICON_SIZE))
        return item

    def _populate_children(self, model: H5Model, path: str, parent_item: QStandardItem) -> None:
        for child in model.list_children(path):
            name_item = self._make_name_item(child, child.name)
            name_item.setData(model, MODEL_ROLE)
            parent_item.appendRow(name_item)
            self._items[(model, child.path)] = name_item
            if child.kind == GROUP and (child.n_children or 0) > 0:
                dummy = QStandardItem("")
                dummy.setEditable(False)
                dummy.setData(True, DUMMY_ROLE)
                name_item.appendRow([dummy])

    def _on_expanded(self, index) -> None:
        item = self.model.itemFromIndex(index)
        if item.rowCount() == 1 and item.child(0).data(DUMMY_ROLE):
            item.removeRow(0)
            node = item.data(NODE_ROLE)
            model = item.data(MODEL_ROLE)
            if node is not None and model is not None:
                self._populate_children(model, node.path, item)
        self._apply_min_width()

    def _on_collapsed(self, _index) -> None:
        self._apply_min_width()

    def _apply_min_width(self) -> None:
        # A hard minimumWidth, not an imperative QSplitter.setSizes() call:
        # setSizes() turned out to get silently overridden by QSplitter's
        # own internal re-layout whenever a child's content changes (the
        # very same event that triggers this), no matter how it was
        # sequenced. minimumWidth is a real constraint QSplitter cannot
        # violate (with setChildrenCollapsible(False) on the parent), so
        # the pane growing to fit falls out naturally instead of being
        # fought for imperatively.
        #
        # The width itself is measured directly with QFontMetrics rather
        # than trusted from header.sectionSize(): a ResizeToContents
        # column, it turns out, adaptively *shrinks* to whatever viewport
        # it's actually given rather than reporting the true width its
        # content needs, so reading it back mid-squeeze just measures the
        # squeeze. Only currently-expanded rows count, since collapsed
        # subtrees aren't visible. Only ever grows, and capped so one
        # deep hierarchy can't swallow the whole window.
        fm = QFontMetrics(self.tree.font())
        indent = self.tree.indentation()
        max_name_px = 0

        def visit(parent_item: Optional[QStandardItem], depth: int) -> None:
            nonlocal max_name_px
            row_count = parent_item.rowCount() if parent_item is not None else self.model.rowCount()
            for r in range(row_count):
                name_item = parent_item.child(r, 0) if parent_item is not None else self.model.item(r, 0)
                if name_item is None or name_item.data(DUMMY_ROLE):
                    continue
                name_px = depth * indent + ICON_SIZE + 16 + fm.horizontalAdvance(name_item.text())
                max_name_px = max(max_name_px, name_px)
                if self.tree.isExpanded(name_item.index()):
                    visit(name_item, depth + 1)

        visit(None, 0)

        width = max_name_px + self.tree.verticalScrollBar().sizeHint().width() + 24
        width = min(width, 700)
        if width > self.minimumWidth():
            self.setMinimumWidth(width)

    def _on_selection_changed(self, _selected, _deselected) -> None:
        indexes = self.tree.selectionModel().selectedRows(0)
        if not indexes:
            return
        item = self.model.itemFromIndex(indexes[0])
        node = item.data(NODE_ROLE)
        model = item.data(MODEL_ROLE)
        if node is not None and model is not None:
            self._on_select(model, node)

    def _on_double_clicked(self, index) -> None:
        item = self.model.itemFromIndex(index)
        if item is None:
            return
        node = item.data(NODE_ROLE)
        model = item.data(MODEL_ROLE)
        if node is not None and model is not None and self._on_activate is not None:
            self._on_activate(model, node)

    def _apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.setStyleSheet(f"HierarchyTree {{ background-color: {palette.base_bg}; }}")
        self.tree.setStyleSheet(f"""
            QTreeView {{
                background-color: {palette.base_bg};
                color: {palette.text};
                border: none;
                outline: 0;
                font-size: 11pt;
            }}
            QTreeView::item {{
                height: 26px;
            }}
            QTreeView::item:hover {{
                background-color: {palette.row_hover};
            }}
            QTreeView::item:selected {{
                background-color: {palette.selection};
                color: {palette.text};
            }}
        """)
        for item in self._items.values():
            node = item.data(NODE_ROLE)
            if node is not None:
                item.setIcon(icons.icon(node.kind, self._icon_color(node.kind), ICON_SIZE))
