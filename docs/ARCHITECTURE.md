# Architecture

This document explains how the grid partition tooling works: components, data flow, algorithms, and known limitations.

## Components
- **KML Parser** (`read_polygon_from_kml`):
  - Extracts the first `Polygon` → `outerBoundaryIs` → `LinearRing` → `coordinates` from a KML file.
  - Produces a list of `(lon, lat)` points (closing point removed if duplicated).

- **Grid Builder** (`build_grid`):
  - Constructs an axis-aligned grid over the polygon’s bounding box.
  - Parameters: `rows`, `cols`; returns cells with `min_lon/max_lon/min_lat/max_lat` plus `row/col` identifiers.

- **Polygon Clipping** (`clip_polygon_with_rect`):
  - Clips the polygon against a cell rectangle using Sutherland–Hodgman (left, right, bottom, top).
  - Deduplicates consecutive points; ensures valid polygon if ≥3 points.

- **KML Writer** (`write_kml`):
  - Writes one `Placemark` per cell with a `Polygon` whose `LinearRing/coordinates` reflect the clipped intersection.
  - Applies a simple line/poly style.

- **Point-in-Polygon** (`point_in_polygon`):
  - Ray casting on `(lon=x, lat=y)` to test whether a waypoint falls inside the polygon.

- **Cell Assignment** (`cell_for_point`):
  - Assigns points to grid cells using inclusive lower bounds and exclusive upper bounds (with an epsilon to include edges).

- **GPX Parser** (`read_gpx`):
  - Loads the GPX root, metadata, and collects all waypoint (`wpt`) elements with their coordinates.
  - Keeps original elements and namespace prefixes.

- **GPX Writer** (`write_gpx`):
  - Creates a GPX 1.1 root using the source `version`/`creator` if present.
  - Deep-copies the original `metadata` element; appends a lightweight `desc` line with the cell label and waypoint count, and sets `keywords` to the source filename.
  - Deep-copies each original `wpt` element to preserve all sub-tags and `extensions`.
  - Optionally draws a rectangle route (`rte` with `rtept` corners) representing cell bounds.

## Data Flow
1. Read polygon from KML → compute bounding box → build grid.
2. Optionally: clip each cell rectangle to polygon and write `grid-areas_{rows}x{cols}.kml`.
3. Read GPX waypoint sources → filter points inside polygon → assign to grid cells.
4. For each cell: write `pois_r{row}_c{col}.gpx` containing original waypoints and an optional bounds rectangle.

## Key Algorithms & Decisions
- **Sutherland–Hodgman** for polygon clipping:
  - Reliable for convex/concave polygons against axis-aligned rectangles.
- **Ray casting** for point containment:
  - Efficient and robust for large waypoint sets.
- **Deep-copy of GPX elements**:
  - Ensures original metadata, namespaces, and extensions remain intact to maximize compatibility.
- **Axis-aligned grid over bounding box**:
  - Simple partitioning; fast and deterministic; pairing with polygon filter guarantees POIs are inside the area even if the rectangle extends beyond.

## Limitations
- Only the KML polygon’s outer boundary is used; holes and multiple polygons are not handled.
- GPX splitting considers `wpt` elements only; routes/tracks are not clipped/split.
- No CRS transforms; coordinates are assumed WGS84.
- Metadata augmentation adds `desc` and `keywords`; if a consumer requires pristine metadata, this can be disabled in code or refined.

## Extensibility
- Equal-area grid: replace linear lat/long steps with geodesic area partitioning.
- Multi-polygon support: read all KML polygons and union/intersect as needed.
- GPX tracks/routes: clip `trkseg/trkpt` and `rte/rtept` by polygon.
- Strict mode: emit metadata exactly as source (no additions) behind a CLI flag.
- GeoJSON: support input/output via GeoJSON with `Polygon`/`FeatureCollection`.

## Files
- [grid_partition.py](../grid_partition.py): unified KML+GPX workflow.
- [build_grid_kml.py](../build_grid_kml.py): standalone KML grid generation.
- [split_pois_grid.py](../split_pois_grid.py): standalone GPX POI splitter.
