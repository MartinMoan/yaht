"""The main content area to the right of the explorer: a rounded,
hairline-bordered card whose frame is *redrawn on top of* its contents.

The dataset table inside runs flush to the panel's edges (see
``DatasetTableView``); left to itself it would paint straight over the
panel's 1px border and rounded corners. ``_PanelFrame`` is a
mouse-transparent overlay kept on top that repaints that border and
refills the four corner cut-outs with the surrounding window colour, so
the card still reads as rounded and framed no matter what fills it.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

import constants as c


class _PanelFrame(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._border = QColor("#30363D")
        self._outside = QColor("#0D1117")

    def set_colors(self, border: str, outside: str) -> None:
        self._border = QColor(border)
        self._outside = QColor(outside)
        self.update()

    def paintEvent(self, event) -> None:
        radius = float(c.PANEL_RADIUS)
        rect = QRectF(self.rect())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Fill just the four corner wedges (full rect minus the rounded
        # rect) with the colour of the gap around the panel.
        wedges = QPainterPath()
        wedges.addRect(rect)
        rounded = QPainterPath()
        rounded.addRoundedRect(rect, radius, radius)
        painter.fillPath(wedges.subtracted(rounded), self._outside)
        # Stroke the 1px rounded border, half a pixel in so it lands
        # fully inside the widget.
        half = c.BORDER_WIDTH / 2.0
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._border, float(c.BORDER_WIDTH)))
        painter.drawRoundedRect(rect.adjusted(half, half, -half, -half), radius, radius)


class ContentPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.frame = _PanelFrame(self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.frame.setGeometry(self.rect())
        self.frame.raise_()
