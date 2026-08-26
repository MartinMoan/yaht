"""Small shared text-formatting helpers with no other home."""
from __future__ import annotations

_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


def format_size(n: int) -> str:
    """Human-readable byte size, scaled up through B/KB/MB/GB/... to
    three significant figures (e.g. "999 B", "118 KB", "14.3 MB",
    "1.00 GB"). 1024-based, matching how most desktop file managers show
    sizes."""
    size = float(max(n, 0))
    unit_index = 0
    while size >= 1024 and unit_index < len(_UNITS) - 1:
        size /= 1024
        unit_index += 1
    unit = _UNITS[unit_index]

    if unit == "B":
        return f"{int(size)} B"
    if size >= 100:
        return f"{size:.0f} {unit}"
    if size >= 10:
        return f"{size:.1f} {unit}"
    return f"{size:.2f} {unit}"
