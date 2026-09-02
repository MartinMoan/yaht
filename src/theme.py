"""Central theming for the Qt rewrite.

The whole point of moving off Tkinter was cross-platform consistency, so
this module forces Qt's "Fusion" style (which Qt draws itself, pixel for
pixel the same regardless of OS) plus a custom QPalette, rather than
letting each platform's native style take over. Light/dark mode follows
the OS where Qt can detect it (``QStyleHints.colorScheme``, Qt 6.5+, with
a live-updating signal), with a manual override exposed via ``set_mode``.
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

import constants as c

POLL_MS = 1500  # fallback only, used if Qt has no colorSchemeChanged signal


def resolve_font_family() -> str:
    available = set(QFontDatabase.families())
    for name in c.FONT_CANDIDATES:
        if name in available:
            return name
    return QApplication.font().family()


class Palette:
    def __init__(self, dark: bool):
        self.dark = dark
        self.text = c.TEXT_DARK if dark else c.TEXT_LIGHT
        self.subtext = c.SUBTEXT_DARK if dark else c.SUBTEXT_LIGHT
        self.header_bg = c.HEADER_BG_DARK if dark else c.HEADER_BG_LIGHT
        self.grid_line = c.GRID_LINE_DARK if dark else c.GRID_LINE_LIGHT
        self.selection = c.SELECTION_DARK if dark else c.SELECTION_LIGHT
        self.accent = c.ACCENT_DARK if dark else c.ACCENT_LIGHT
        self.row_hover = c.ROW_HOVER_DARK if dark else c.ROW_HOVER_LIGHT
        self.splitter = c.SPLITTER_DARK if dark else c.SPLITTER_LIGHT
        self.columns = c.COLUMN_PALETTE_DARK if dark else c.COLUMN_PALETTE_LIGHT
        self.chart_series = c.CHART_SERIES_DARK if dark else c.CHART_SERIES_LIGHT
        self.error = c.ERROR_COLOR_DARK if dark else c.ERROR_COLOR_LIGHT
        # Shared surface of *both* framed panels (explorer + content) --
        # index 0 of the column palette, the darkest surface in the app.
        # The rounded panel widgets don't paint their own corners (a
        # styled border-radius clips them), so the corner wedges just show
        # the window_bg gap behind, with no colour mismatch.
        self.body_bg = self.columns[0]
        self.sidebar_bg = self.body_bg
        # An element raised above that surface: unselected tabs, table
        # headers, group-overview rows.
        self.raised_bg = c.RAISED_BG_DARK if dark else c.RAISED_BG_LIGHT
        # Everything *outside* the panels: the window frame, the gap
        # around and between them, and the title bar.
        self.window_bg = "#0D1117" if dark else "#F5F5F7"
        self.base_bg = "#0D1117" if dark else "#FFFFFF"
        self.button_bg = "#21262D" if dark else "#EDEDF0"
        # Semantic alias -- GRID_LINE_* doubles as the theme's border
        # color for every hairline in the app (panel borders, menu
        # borders, table gridlines, ...).
        self.border = self.grid_line
        self.radius = c.PANEL_RADIUS

    def column_color(self, index: int) -> str:
        return self.columns[index % len(self.columns)]

    def chart_color(self, index: int) -> str:
        # A vivid line/marker color for a plotted series -- see
        # CHART_SERIES_LIGHT/DARK in constants.py for why this isn't just
        # column_color() reused.
        return self.chart_series[index % len(self.chart_series)]


class ThemeManager(QObject):
    changed = Signal(object)  # emits the new Palette

    def __init__(self, app: QApplication):
        super().__init__()
        self._app = app
        self.font_family = resolve_font_family()
        self._mode_override: Optional[bool] = None  # None=follow OS, else True/False
        self._listeners: list[Callable[[Palette], None]] = []

        self._dark = self._detect_dark()
        self.palette = Palette(self._dark)
        self._apply_qapp_style()

        style_hints = app.styleHints()
        if hasattr(style_hints, "colorSchemeChanged"):
            style_hints.colorSchemeChanged.connect(lambda _s: self._refresh())
        else:
            timer = QTimer(self)
            timer.timeout.connect(self._refresh)
            timer.start(POLL_MS)
            self._poll_timer = timer

    def register(self, callback: Callable[[Palette], None]) -> None:
        """Subscribe to appearance changes. Called immediately with the
        current palette so widgets don't need a separate initial apply."""
        self._listeners.append(callback)
        callback(self.palette)

    def set_mode(self, mode: str) -> None:
        """``mode`` is one of "system", "light", "dark"."""
        self._mode_override = None if mode == "system" else (mode == "dark")
        self._refresh()

    def _detect_dark(self) -> bool:
        try:
            scheme = self._app.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return True
            if scheme == Qt.ColorScheme.Light:
                return False
        except Exception:
            pass
        return self._app.palette().color(QPalette.ColorRole.Window).lightness() < 128

    def _refresh(self) -> None:
        dark = self._mode_override if self._mode_override is not None else self._detect_dark()
        if dark == self._dark:
            return
        self._dark = dark
        self.palette = Palette(dark)
        self._apply_qapp_style()
        for cb in self._listeners:
            cb(self.palette)
        self.changed.emit(self.palette)

    def _apply_qapp_style(self) -> None:
        self._app.setStyle("Fusion")
        p = self.palette
        qp = QPalette()
        Role = QPalette.ColorRole
        qp.setColor(Role.Window, QColor(p.window_bg))
        qp.setColor(Role.WindowText, QColor(p.text))
        qp.setColor(Role.Base, QColor(p.base_bg))
        qp.setColor(Role.AlternateBase, QColor(p.row_hover))
        qp.setColor(Role.Text, QColor(p.text))
        qp.setColor(Role.Button, QColor(p.button_bg))
        qp.setColor(Role.ButtonText, QColor(p.text))
        # `selection`, not `accent`: this is the flat highlight the style
        # paints behind selected rows / text runs / the tree's branch
        # column, and it needs to match the rounded selection pills the
        # sidebar and the tab bar draw with `palette.selection`.
        qp.setColor(Role.Highlight, QColor(p.selection))
        qp.setColor(Role.HighlightedText, QColor(p.text))
        qp.setColor(Role.ToolTipBase, QColor(p.base_bg))
        qp.setColor(Role.ToolTipText, QColor(p.text))
        qp.setColor(Role.PlaceholderText, QColor(p.subtext))
        disabled_text = QColor(p.subtext)
        qp.setColor(QPalette.ColorGroup.Disabled, Role.Text, disabled_text)
        qp.setColor(QPalette.ColorGroup.Disabled, Role.WindowText, disabled_text)
        qp.setColor(QPalette.ColorGroup.Disabled, Role.ButtonText, disabled_text)
        self._app.setPalette(qp)
        self._app.setFont(QFont(self.font_family, 10))
