"""Loads a user-supplied offline basemap file for the graph "Map" mode
(see ``core/plotting.build_map_plotly_spec``). Two kinds of file are
supported:

* Vector (``.geojson``/``.json``) -- parsed with the stdlib ``json``
  module and turned into extra Plotly trace dicts (plain cartesian lon/
  lat line/fill traces, not ``scattergeo`` -- see
  ``core/plotting.build_map_plotly_spec`` for why), e.g. a coastline or
  reference boundary. No image involved. Coordinates are assumed to be
  plain WGS84 lon/lat degrees (the GeoJSON default) unless the file's
  legacy ``"crs"`` member names a UTM zone (EPSG:326xx/327xx/258xx --
  the projected, metric coordinate system many national mapping
  agencies, e.g. Norway's Kartverket, export in by default), which is
  converted to lon/lat via a closed-form inverse transverse-Mercator
  formula (see ``_utm_to_lonlat``). Any other declared CRS raises a
  clear error rather than silently misplacing every coordinate --
  reprojecting to EPSG:4326 in QGIS/ogr2ogr first is the fallback, same
  as for anything else genuinely out of scope here.
* Raster (``.png``/``.jpg``/``.jpeg``/``.tif``/``.tiff``) -- a plain
  image, georeferenced either by a sidecar "world file"
  (``.pgw``/``.jgw``/``.tfw``/``.wld`` -- a 6-line affine transform, the
  common GDAL-free way to georeference an image) or, for ``.tif``/
  ``.tiff`` without one, by reading GeoTIFF's own embedded
  ModelPixelScale/ModelTiepoint tags directly via Pillow (covers the
  common north-up, unrotated, plain lat/lon case with zero extra
  dependencies).

Deliberately dependency-light (stdlib ``json`` + the Pillow this app
already uses for ``icons.py``) rather than pulling in GDAL/rasterio/
pyproj, matching this codebase's general aversion to heavy/fragile
dependencies (see e.g. the scattergl-avoidance note in
``core/plotting._trace_type_mode``). Arbitrary-CRS reprojection and
formats like BSB/KAP or Shapefile are explicitly out of scope -- see the
graphing plan.
"""
from __future__ import annotations

import base64
import io
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PIL import Image

# A safety cap on individual geometries surviving crop_vector_to_view's
# bounding-box filter, for a pathologically detailed chart even within
# the padded view -- see the comment where it's used.
_MAX_VECTOR_GEOMETRIES = 6000

_RASTER_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
_WORLD_FILE_EXTS = {
    ".png": ".pgw",
    ".jpg": ".jgw",
    ".jpeg": ".jgw",
    ".tif": ".tfw",
    ".tiff": ".tfw",
}
# GeoTIFF tags (OGC GeoTIFF spec) -- read directly since Pillow exposes
# raw TIFF tags without needing any GDAL-style GeoTIFF support.
_TAG_MODEL_PIXEL_SCALE = 33550
_TAG_MODEL_TIEPOINT = 33922


class BasemapError(ValueError):
    """A basemap file couldn't be loaded -- message is user-facing."""


@dataclass(frozen=True)
class BasemapResult:
    kind: str  # "raster" or "vector"
    # Raster only -- kept as a loaded PIL Image rather than an
    # already-encoded data URI, so the caller can crop it down to just
    # the region actually being plotted (see crop_raster_to_view) before
    # paying to encode/embed/render it. A basemap file can cover a much
    # larger area than the data ever does, and embedding the whole thing
    # at full resolution was what made pan/zoom sluggish.
    image: Optional["Image.Image"] = None
    lon_min: Optional[float] = None
    lon_max: Optional[float] = None
    lat_min: Optional[float] = None
    lat_max: Optional[float] = None
    extra_traces: list = field(default_factory=list)


def load_basemap(path: str) -> BasemapResult:
    ext = Path(path).suffix.lower()
    if ext in (".geojson", ".json"):
        return _load_vector(path)
    if ext in _RASTER_EXTS:
        return _load_raster(path, ext)
    raise BasemapError(
        f"Unsupported basemap file type '{ext}'. Supported: GeoJSON (.geojson), "
        "or a georeferenced image -- PNG/JPEG/TIFF with a matching .pgw/.jgw/.tfw/.wld "
        "world file, or a GeoTIFF with embedded georeferencing tags."
    )


def _epsg_code_from_crs(crs: Optional[dict]) -> Optional[int]:
    if not crs:
        return None
    name = crs.get("properties", {}).get("name", "")
    if not name:
        return None
    if "CRS84" in name.upper():
        return 4326
    if "EPSG" not in name.upper():
        return None
    # Handles both the plain "EPSG:25832" form and the URN form this
    # legacy GeoJSON "crs" member commonly uses, e.g.
    # "urn:ogc:def:crs:EPSG::25832" (or, with a version segment,
    # "urn:ogc:def:crs:EPSG:8.9:25832") -- the EPSG code is always the
    # trailing digit run either way.
    match = re.search(r"(\d+)\s*$", name)
    return int(match.group(1)) if match else None


def _utm_zone_from_epsg(epsg: int) -> Optional[tuple]:
    if 32601 <= epsg <= 32660:
        return epsg - 32600, True  # WGS84 / UTM zone N, northern hemisphere
    if 32701 <= epsg <= 32760:
        return epsg - 32700, False  # WGS84 / UTM zone N, southern hemisphere
    if 25828 <= epsg <= 25838:
        return epsg - 25800, True  # ETRS89 / UTM zone N -- covers Europe, always northern
    return None


def _utm_to_lonlat(easting: float, northing: float, zone: int, northern: bool) -> tuple:
    """Closed-form inverse transverse Mercator (Snyder's standard UTM
    formulas), using WGS84/GRS80 ellipsoid constants -- the two datums
    differ by sub-millimeters, irrelevant at basemap-display precision.
    A real, well-established formula rather than an approximation, and
    the reason UTM specifically is supported without pulling in pyproj/
    GDAL: it's the one non-degrees CRS common enough (national mapping
    agencies across Europe, the US, etc. routinely export in it) and
    simple enough in closed form to be worth building in directly.
    """
    a = 6378137.0
    f = 1 / 298.257223563
    e2 = f * (2 - f)
    e_prime2 = e2 / (1 - e2)
    k0 = 0.9996

    x = easting - 500000.0
    y = northing if northern else northing - 10_000_000.0

    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))

    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )

    n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    t1 = math.tan(phi1) ** 2
    c1 = e_prime2 * math.cos(phi1) ** 2
    r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * k0)

    lat = phi1 - (n1 * math.tan(phi1) / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * e_prime2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * e_prime2 - 3 * c1**2) * d**6 / 720
    )
    lon = (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * e_prime2 + 24 * t1**2) * d**5 / 120
    ) / math.cos(phi1)

    central_meridian = math.radians((zone - 1) * 6 - 180 + 3)
    return math.degrees(lon + central_meridian), math.degrees(lat)


def _load_vector(path: str) -> BasemapResult:
    with open(path, "r", encoding="utf-8") as f:
        geojson = json.load(f)

    epsg = _epsg_code_from_crs(geojson.get("crs"))
    transform: Optional[Callable] = None
    if epsg is not None and epsg != 4326:
        zone_info = _utm_zone_from_epsg(epsg)
        if zone_info is None:
            raise BasemapError(
                f"This GeoJSON's coordinates are in EPSG:{epsg}, which isn't supported directly -- "
                "only plain WGS84 (EPSG:4326) or a UTM zone are. Reproject it to EPSG:4326 first "
                "(e.g. in QGIS: Layer -> Export -> Save Features As..., set CRS to EPSG:4326; or "
                f"ogr2ogr -t_srs EPSG:4326 output.geojson input.geojson)."
            )
        zone, northern = zone_info
        transform = lambda x, y: _utm_to_lonlat(x, y, zone, northern)  # noqa: E731

    def _xy(coord: list) -> tuple:
        x, y = coord[0], coord[1]
        return transform(x, y) if transform else (x, y)

    traces: list = []

    def walk(geometry: dict) -> None:
        gtype = geometry.get("type")
        coords = geometry.get("coordinates")
        if gtype == "Point":
            lon, lat = _xy(coords)
            traces.append(
                {
                    "type": "scatter",
                    "mode": "markers",
                    "x": [lon],
                    "y": [lat],
                    "showlegend": False,
                    "name": "",
                }
            )
        elif gtype == "LineString":
            pts = [_xy(c) for c in coords]
            traces.append(
                {
                    "type": "scatter",
                    "mode": "lines",
                    "x": [p[0] for p in pts],
                    "y": [p[1] for p in pts],
                    "showlegend": False,
                    "name": "",
                }
            )
        elif gtype == "Polygon":
            for ring in coords:
                pts = [_xy(c) for c in ring]
                traces.append(
                    {
                        "type": "scatter",
                        # Outline only, no fill -- a GeoJSON polygon ring
                        # is already closed (first point == last per the
                        # spec), so this still reads as a closed shape.
                        # Filling it solid was the actual bug behind
                        # "gibberish" real-world renders: a file with
                        # many overlapping polygons (e.g. bathymetric
                        # depth-contour bands, or one large sea-surface/
                        # coverage polygon) each filled opaque in a
                        # different color piled into an unreadable mess
                        # -- a basemap should read as background
                        # geography, not dominate the plot.
                        "mode": "lines",
                        "x": [p[0] for p in pts],
                        "y": [p[1] for p in pts],
                        "showlegend": False,
                        "name": "",
                    }
                )
        elif gtype in ("MultiPoint", "MultiLineString", "MultiPolygon"):
            single = gtype[len("Multi") :]
            for part in coords:
                walk({"type": single, "coordinates": part})
        elif gtype == "GeometryCollection":
            for geom in geometry.get("geometries", []):
                walk(geom)

    features = geojson.get("features", [geojson]) if geojson.get("type") == "FeatureCollection" else [geojson]
    for feature in features:
        geometry = feature.get("geometry", feature)
        if geometry:
            walk(geometry)

    return BasemapResult(kind="vector", extra_traces=traces)


def crop_vector_to_view(
    basemap: BasemapResult, lon_range: tuple, lat_range: tuple, padding_deg: float = 0.3
) -> list:
    """Returns just the subset of ``basemap.extra_traces`` whose own
    bounding box intersects the lon/lat view (the plotted data's own
    bounding box, expanded by a flat ``padding_deg`` in every direction)
    -- so a large GeoJSON file (e.g. a whole coastline made of many
    segments) doesn't get embedded and re-rendered in full on every pan/
    zoom when the plotted data only covers a small regional area, the
    same problem ``crop_raster_to_view`` solves for a raster basemap.

    ``padding_deg`` is a flat margin, not a fraction of the plotted
    data's own span -- scaling it relative to the data's span badly
    under-served a short/small track (e.g. a few hundred meters of GPS
    log): the margin shrank right along with it, leaving almost nothing
    of a real coastline/depth-contour file close enough to survive the
    filter. A flat degrees value gives a consistent, meaningful amount
    of surrounding map regardless of how small the plotted data is; see
    ``MapConfig.basemap_padding_deg`` for where the user controls it.

    A geometry that only *partially* overlaps the view (e.g. one very
    long segment passing through the region) is kept whole rather than
    clipped to just the visible portion -- real-world boundary/coastline
    files are typically split into many smaller features already, so
    this bounding-box filter alone removes the vast majority of
    off-screen data without needing true polyline/polygon clipping.
    """
    lon_min, lon_max = lon_range
    lat_min, lat_max = lat_range
    view_lon = (lon_min - padding_deg, lon_max + padding_deg)
    view_lat = (lat_min - padding_deg, lat_max + padding_deg)

    kept = []
    for trace in basemap.extra_traces:
        xs, ys = trace.get("x"), trace.get("y")
        if not xs or not ys:
            continue
        if max(xs) < view_lon[0] or min(xs) > view_lon[1]:
            continue
        if max(ys) < view_lat[0] or min(ys) > view_lat[1]:
            continue
        kept.append(trace)

    if len(kept) > _MAX_VECTOR_GEOMETRIES:
        # A safety net for a pathologically detailed chart (e.g. a dense
        # hydrographic survey with a generous padding radius) that still
        # has thousands of individual geometries even after the bounding-
        # box filter above -- evenly thin them out rather than let the
        # count grow unbounded. Doesn't reorder anything, so neighboring
        # geometries (usually spatially related, e.g. adjacent depth-
        # contour segments) are still dropped somewhat evenly rather than
        # all from one area.
        stride = -(-len(kept) // _MAX_VECTOR_GEOMETRIES)  # ceil division
        kept = kept[::stride]
    return kept


def merge_vector_traces(traces: list) -> list:
    """Consolidates many small per-geometry trace dicts (one per Point/
    LineString/Polygon-ring, from ``_load_vector`` -- or a
    ``crop_vector_to_view``-filtered subset of them) into just a
    handful of traces, one per draw mode ("lines", "markers"), joined
    with a ``None`` separator between each original geometry so Plotly
    still draws them as visually distinct disconnected pieces.

    This is what actually fixes slow pan/zoom on a real basemap file,
    not the crop above: a real chart can easily contain thousands of
    small geometries (every depth-contour band, every skerry outline),
    and Plotly's *per-trace* overhead -- a separate SVG path, its own
    event handlers, its own legend entry -- dominates render cost far
    more than total point count does. The crop limits how much geometry
    is included at all; this fixes how expensive that geometry is to
    draw once it is. Since every vector-basemap trace already shares one
    plain outline style (see build_map_plotly_spec -- no per-geometry
    fill or color survives that step anyway), merging them changes
    nothing about how the map looks, only how many separate objects the
    browser has to manage.
    """
    by_mode: dict = {}
    for trace in traces:
        mode = trace.get("mode", "lines")
        bucket = by_mode.setdefault(mode, {"x": [], "y": []})
        if bucket["x"]:
            bucket["x"].append(None)
            bucket["y"].append(None)
        bucket["x"].extend(trace["x"])
        bucket["y"].extend(trace["y"])

    return [
        {"type": "scatter", "mode": mode, "x": bucket["x"], "y": bucket["y"], "showlegend": False, "name": ""}
        for mode, bucket in by_mode.items()
    ]


def _load_raster(path: str, ext: str) -> BasemapResult:
    world_path = Path(path).with_suffix(_WORLD_FILE_EXTS[ext])
    if world_path.exists():
        bounds = _read_world_file(world_path, path)
    elif ext in (".tif", ".tiff"):
        bounds = _read_geotiff_bounds(path)
    else:
        raise BasemapError(
            f"No matching world file found ({world_path.name}) -- a PNG/JPEG basemap needs one "
            "alongside it to be georeferenced. TIFF files can alternatively carry their own "
            "embedded GeoTIFF georeferencing tags."
        )

    img = Image.open(path)
    img.load()  # force the read now -- the file handle doesn't need to stay open

    lon_min, lon_max, lat_min, lat_max = bounds
    return BasemapResult(
        kind="raster", image=img, lon_min=lon_min, lon_max=lon_max, lat_min=lat_min, lat_max=lat_max
    )


def crop_raster_to_view(
    basemap: BasemapResult, lon_range: tuple, lat_range: tuple, padding_deg: float = 0.3
) -> tuple:
    """Crops ``basemap.image`` down to just the region covering
    ``lon_range``/``lat_range`` (the data actually being plotted),
    expanded by a flat ``padding_deg`` margin in every direction (see
    ``crop_vector_to_view`` for why this is a flat degrees value rather
    than a fraction of the plotted data's own span), then encodes just
    that crop to a PNG data URI. Falls back to the whole image if the
    requested range doesn't overlap it at all.

    A basemap file can cover a much larger area than the plotted data
    ever does -- embedding the *whole* file as one Plotly background
    image meant the browser was decoding/rescaling a huge bitmap on
    every pan/zoom, which is what made those interactions sluggish.
    Cropping to the region that's actually in view keeps the embedded
    image proportional to the data instead.
    """
    full_lon_span = basemap.lon_max - basemap.lon_min
    full_lat_span = basemap.lat_max - basemap.lat_min

    req_lon_min, req_lon_max = lon_range
    req_lat_min, req_lat_max = lat_range
    lon_min = max(req_lon_min - padding_deg, basemap.lon_min)
    lon_max = min(req_lon_max + padding_deg, basemap.lon_max)
    lat_min = max(req_lat_min - padding_deg, basemap.lat_min)
    lat_max = min(req_lat_max + padding_deg, basemap.lat_max)

    width, height = basemap.image.size
    cropped = None
    if lon_min < lon_max and lat_min < lat_max and full_lon_span and full_lat_span:
        left = max(0, int((lon_min - basemap.lon_min) / full_lon_span * width))
        right = min(width, int((lon_max - basemap.lon_min) / full_lon_span * width))
        # Image row 0 is the top (north / lat_max), so higher latitude
        # means a smaller row index.
        top = max(0, int((basemap.lat_max - lat_max) / full_lat_span * height))
        bottom = min(height, int((basemap.lat_max - lat_min) / full_lat_span * height))
        if right > left and bottom > top:
            cropped = basemap.image.crop((left, top, right, bottom))

    if cropped is None:
        # The requested view doesn't usefully overlap the image (or fell
        # entirely outside it after clamping) -- fall back to the whole
        # thing rather than an inverted/empty crop.
        cropped = basemap.image
        lon_min, lon_max, lat_min, lat_max = basemap.lon_min, basemap.lon_max, basemap.lat_min, basemap.lat_max

    buf = io.BytesIO()
    cropped.convert("RGBA").save(buf, format="PNG")
    data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return data_uri, lon_min, lon_max, lat_min, lat_max


def _read_world_file(world_path: Path, image_path: str) -> tuple:
    with open(world_path, "r", encoding="utf-8") as f:
        values = [float(line.strip()) for line in f if line.strip()]
    if len(values) != 6:
        raise BasemapError(f"'{world_path.name}' doesn't look like a valid world file (expected 6 lines).")
    px_size_x, _rot1, _rot2, px_size_y, origin_x, origin_y = values

    with Image.open(image_path) as img:
        width, height = img.size

    lon_min = origin_x
    lon_max = origin_x + width * px_size_x
    lat_max = origin_y
    lat_min = origin_y + height * px_size_y  # px_size_y is negative for a north-up image
    return (min(lon_min, lon_max), max(lon_min, lon_max), min(lat_min, lat_max), max(lat_min, lat_max))


def _read_geotiff_bounds(path: str) -> tuple:
    with Image.open(path) as img:
        tags = getattr(img, "tag_v2", None)
        width, height = img.size
        if tags is None or _TAG_MODEL_PIXEL_SCALE not in tags or _TAG_MODEL_TIEPOINT not in tags:
            raise BasemapError(
                f"'{Path(path).name}' has no matching world file and no embedded GeoTIFF "
                "georeferencing tags -- add a .tfw world file alongside it to use it as a basemap."
            )
        scale = tags[_TAG_MODEL_PIXEL_SCALE]
        tiepoint = tags[_TAG_MODEL_TIEPOINT]
        px_scale_x, px_scale_y = float(scale[0]), float(scale[1])
        # Tiepoint is (pixel_x, pixel_y, pixel_z, model_x, model_y, model_z);
        # the common case has the first tiepoint at pixel (0, 0).
        model_x, model_y = float(tiepoint[3]), float(tiepoint[4])

    lon_min = model_x
    lon_max = model_x + width * px_scale_x
    lat_max = model_y
    lat_min = model_y - height * px_scale_y
    return (min(lon_min, lon_max), max(lon_min, lon_max), min(lat_min, lat_max), max(lat_min, lat_max))
