# Sweden Trip Grid Tools

Unified tooling to partition a KML-defined area into a grid and split GPX POIs into per-cell files. It preserves original GPX metadata and adds optional visual rectangles.

## Prerequisites
- Python 3.9+ (macOS)
- Files in this workspace:
  - `grid_partition.py` (unified tool)
  - `build_grid_kml.py` (KML-only grid generator)
  - `split_pois_grid.py` (GPX-only splitter)
  - `Unbenannte Karte.kml` (input polygon)
  - `CampWild Places.gpx` and optional `TET/*.gpx` (POI sources)

## Quick Start
Generate both KML and per-cell GPX for a 6×3 grid over your polygon, using CampWild POIs, with a rectangle route drawn in each output:

```bash
python3 "/Users/gerald/Documents/Urlaub/2026 Schweden Motorrad/grid_partition.py" --rows 6 --cols 3 --input-kml "Unbenannte Karte.kml" --input-gpx "CampWild Places.gpx" --emit-kml --emit-gpx --draw-rect
```

Outputs:
- KML: `grid-areas_6x3.kml`
- GPX folder: `grid-pois-6x3/` with files like `pois_r1_c1.gpx` … `pois_r6_c3.gpx`

## Usage (Unified)
`grid_partition.py` options:
- `--rows N`: number of grid rows (default 5)
- `--cols N`: number of grid columns (default 2)
- `--input-kml PATH`: KML file containing a polygon (outer boundary)
- `--input-gpx PATH [PATH ...]`: one or more GPX files to include as POI sources
- `--emit-kml`: write a clipped grid KML named `grid-areas_{rows}x{cols}.kml`
- `--emit-gpx`: write per-cell GPX files in `grid-pois-{rows}x{cols}/`
- `--out-kml PATH`: custom KML output path
- `--out-gpx-dir PATH`: custom GPX output directory
- `--draw-rect`: draw a rectangle route (`rte`/`rtept`) per cell in each GPX

Examples:
- KML only (7×3):
```bash
python3 "/Users/gerald/Documents/Urlaub/2026 Schweden Motorrad/grid_partition.py" --rows 7 --cols 3 --input-kml "Unbenannte Karte.kml" --emit-kml
```
- GPX only (6×3), multiple sources, rectangles on:
```bash
python3 "/Users/gerald/Documents/Urlaub/2026 Schweden Motorrad/grid_partition.py" --rows 6 --cols 3 --input-kml "Unbenannte Karte.kml" --input-gpx "CampWild Places.gpx" "TET/N.gpx" "TET/S.gpx" --emit-gpx --draw-rect
```

## Behavior & Assumptions
- Reads the first `Polygon` in the KML and uses its outer boundary.
- Builds an axis-aligned grid over the polygon’s bounding box.
- KML output clips each grid cell rectangle to the polygon (Sutherland–Hodgman).
- GPX splitting:
  - Considers waypoint elements (`wpt`) only; routes/tracks are ignored.
  - Filters POIs to those inside the polygon (ray casting), then assigns to grid cells.
  - Deep-copies original waypoint elements and preserves GPX metadata; appends cell label and count to `metadata/desc` and adds `metadata/keywords` with the source filename.
  - Optionally draws a bounds rectangle as a `rte` in each output GPX.

## Troubleshooting
- If a viewer rejects files, disable rectangle drawing (`--draw-rect` not set) or request a "strict" variant with no metadata modifications.
- Ensure inputs are valid: KML polygon coordinates as `lon,lat[,alt]`; GPX waypoints with `lat`/`lon`.

## Related Scripts
- [grid_partition.py](grid_partition.py): unified tool
- [build_grid_kml.py](build_grid_kml.py): KML grid generator
- [split_pois_grid.py](split_pois_grid.py): POI splitter

## License
Internal workspace tooling for trip planning.
