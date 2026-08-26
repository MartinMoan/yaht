"""Left-hand explorer pane: a lazily-populated group/dataset tree, similar
in spirit to VS Code's file explorer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTreeView, QVBoxLayout, QWidget

import icons
from core.h5_model import DATASET, GROUP, H5Model, NodeInfo
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

    def load_files(self, models: list[H5Model]) -> None:
        """Populates the tree with one root item per model, each file's
        own group hierarchy nested beneath it -- so several files can be
        browsed side by side, e.g. every .h5 file found in a directory."""
        self.clear()
        for model in models:
            root_info = model.root_info()
            root_item = self._make_name_item(root_info, Path(model.path).name)
            root_item.setData(model, MODEL_ROLE)
            self.model.appendRow(root_item)
            self._items[(model, "/")] = root_item
            self._populate_children(model, "/", root_item)

        if self.model.rowCount():
            first_root = self.model.item(0)
            self.tree.expand(first_root.index())
            self.tree.setCurrentIndex(first_root.index())  # triggers _on_selection_changed
        self._apply_min_width()

    def clear(self) -> None:
        self.model.removeRows(0, self.model.rowCount())
        self._items.clear()

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
