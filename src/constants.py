"""Shared visual constants: fonts, sizing and the column color palette.

Colors are defined as (light, dark) pairs so the rest of the app can pick
the right one for the current appearance mode without any widget needing
to know the palette itself.
"""
from __future__ import annotations

APP_NAME = "YAHT"

# File extensions treated as HDF5 files -- both by the file-open dialog's
# listing/completion and by directory scanning (CLI args, "open every
# .h5 file in this folder").
H5_SUFFIXES = {".h5", ".hdf5", ".he5"}

ROW_HEIGHT = 27
HEADER_HEIGHT = 32
INDEX_COL_WIDTH = 60
MIN_COL_WIDTH = 90
MAX_COL_WIDTH = 260

# Shared corner radius + hairline border for the top-level chrome: the
# frameless window itself and the two panels it frames (the left explorer
# and the main content area). Matched to the "GitHub Dark Default" VS Code
# theme's panel treatment -- a small radius with a 1px border in the
# theme's own border color (see GRID_LINE_* below, which doubles as the
# border color everywhere in the app).
PANEL_RADIUS = 8
BORDER_WIDTH = 1
# Gap left between the two framed panels and the window's own outer
# border, so each panel reads as a separate rounded card floating on the
# window rather than a second border stacked against the frame's.
WINDOW_PADDING = 8

# Fonts to try, in order, before giving up and letting Qt pick its
# platform default. Segoe UI / SF cover stock Windows/macOS; the rest are
# common Linux desktop fallbacks.
FONT_CANDIDATES = [
    "Segoe UI",
    "SF Pro Text",
    "Helvetica Neue",
    "Inter",
    "Roboto",
    "Ubuntu",
    "Noto Sans",
    "Cantarell",
    "DejaVu Sans",
    "Arial",
]

# Number of rows fetched from disk per background read. Small enough to
# stay responsive while scrolling, large enough to amortize h5py call
# overhead.
ROW_BLOCK_SIZE = 200

# How many blocks (i.e. ROW_BLOCK_SIZE * this) to keep resident in memory
# per open dataset view before evicting least-recently-used blocks.
MAX_CACHED_BLOCKS = 400

# Safety cap on the number of flattened columns we will ever try to render
# for a single dataset (very wide / high-rank datasets get truncated with
# a warning rather than freezing the UI).
MAX_COLUMNS = 256

# Hard cap on rows read into memory for a "graph selected columns" plot.
# This is a one-shot bulk read via h5_model.read_rows(), independent of
# the table's own ROW_BLOCK_SIZE/MAX_CACHED_BLOCKS paging cache -- kept
# well under that cache's own 80,000-row resident cap, and low enough to
# keep SVG-mode Plotly traces (Line/Bar/Histogram) panning/zooming
# smoothly without needing WebGL for every trace type.
MAX_PLOT_ROWS = 20_000

# Background colors used to tint alternating columns so it's easy to track
# a column while scrolling vertically through a large table.
COLUMN_PALETTE_LIGHT = [
    "#FFFFFF",
    "#F2F6FC",
    "#EEF7F1",
    "#FCF3EC",
    "#F6F0FA",
    "#EFFAFA",
]
# Dark tints hug the panel surface (#010409 -- the explorer and content
# panels share it), index-aligned with CHART_SERIES_DARK's hue families
# (blue/green/orange/purple/teal) so a plotted series still echoes its
# column's tint.
COLUMN_PALETTE_DARK = [
    "#010409",
    "#03080F",
    "#020E09",
    "#0E0804",
    "#090510",
    "#010E0D",
]

# Text colors for header / body per appearance mode. Dark values are
# lifted from the "GitHub Dark Default" VS Code theme.
TEXT_LIGHT = "#1A1A1A"
TEXT_DARK = "#E6EDF3"  # theme `foreground`
SUBTEXT_LIGHT = "#6B6B6B"
SUBTEXT_DARK = "#7D8590"  # theme `descriptionForeground`

HEADER_BG_LIGHT = "#E5E9F0"
HEADER_BG_DARK = "#010409"  # theme `sideBar.background` -- recessed chrome in the dialogs

# An element raised *above* the panel surface: unselected tabs sit on it
# implicitly, group-overview rows and table headers use it directly. The
# panels themselves are the darkest surface (COLUMN_PALETTE_*[0]), so
# "raised" is the lighter editor colour.
RAISED_BG_LIGHT = "#E5E9F0"
RAISED_BG_DARK = "#0D1117"

GRID_LINE_LIGHT = "#DDE1E8"
GRID_LINE_DARK = "#30363D"  # theme border color (`*.border` everywhere)

SELECTION_LIGHT = "#E6E4FB"
SELECTION_DARK = "#343941"  # theme `list.activeSelectionBackground` (#6E768166) flattened onto the bg

# Accent used for the active/interactive accents that aren't covered by
# the CTk color theme itself (ttk selection, splitter drag feedback,
# dataset-type icon tint).
ACCENT_LIGHT = "#4F46E5"
ACCENT_DARK = "#1F6FEB"  # theme `focusBorder` / `progressBar.background`

ROW_HOVER_LIGHT = "#F1F1F6"
ROW_HOVER_DARK = "#161B22"  # theme `editorWidget.background` -- the subtle surface lift

SPLITTER_LIGHT = "#E3E5EA"
SPLITTER_DARK = "#30363D"

# Truncation/warning text color -- used both for the dataset table's
# "showing first N of M flattened columns" notice and the graph window's
# "showing first N of M rows" notice.
WARN_COLOR_LIGHT = "#8A5A00"
WARN_COLOR_DARK = "#D29922"  # theme `editorWarning.foreground`

# Non-fatal error text (status bar message slot, dialog error labels).
ERROR_COLOR_LIGHT = "#C0392B"
ERROR_COLOR_DARK = "#F85149"  # theme `errorForeground`

# Vivid line/marker colors for the graph window, index-aligned with
# COLUMN_PALETTE_* so a plotted series' color still matches the hue family
# of its column's tint in the table -- but NOT the same colors: those are
# deliberately near-invisible tints meant to sit almost flush with the
# table's own background (e.g. dark index 1 "#03080F" vs body_bg
# "#010409"), which made an actual plotted line nearly invisible against
# the chart background when reused directly as a line color.
CHART_SERIES_LIGHT = [
    ACCENT_LIGHT,  # index 0 (the default/unstyled column) -- no real hue of its own
    "#2563EB",  # blue
    "#059669",  # green
    "#D97706",  # orange
    "#7C3AED",  # purple
    "#0D9488",  # teal
]
CHART_SERIES_DARK = [
    ACCENT_DARK,
    "#58A6FF",  # blue   -- theme `terminal.ansiBlue`
    "#3FB950",  # green  -- theme `terminal.ansiGreen`
    "#D29922",  # orange -- theme `terminal.ansiYellow`
    "#BC8CFF",  # purple -- theme `terminal.ansiMagenta`
    "#39C5CF",  # teal   -- theme `terminal.ansiCyan`
]
