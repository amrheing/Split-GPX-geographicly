#!/usr/bin/env python3
import os
import argparse
import copy
import xml.etree.ElementTree as ET
from typing import List, Tuple, Dict, Optional

GPX_NS = 'http://www.topografix.com/GPX/1/1'
KML_NS = 'http://www.opengis.net/kml/2.2'

# ---------------- KML helpers ----------------

def read_polygon_from_kml(kml_path: str) -> List[Tuple[float, float]]:
    tree = ET.parse(kml_path)
    root = tree.getroot()
    coords_elem = root.find(f'.//{{{KML_NS}}}Polygon/{{{KML_NS}}}outerBoundaryIs/{{{KML_NS}}}LinearRing/{{{KML_NS}}}coordinates')
    if coords_elem is None or not coords_elem.text:
        raise ValueError('No polygon coordinates found in KML')
    coords_text = coords_elem.text.strip()
    points: List[Tuple[float, float]] = []
    for token in coords_text.split():
        parts = token.split(',')
        if len(parts) < 2:
            continue
        lon = float(parts[0])
        lat = float(parts[1])
        points.append((lon, lat))
    if points and points[0] == points[-1]:
        points = points[:-1]
    return points


def polygon_bbox(poly: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    lons = [p[0] for p in poly]
    lats = [p[1] for p in poly]
    return min(lons), max(lons), min(lats), max(lats)

# Sutherland–Hodgman polygon clipping against axis-aligned rectangular window

def intersect_segment_with_vertical(p1: Tuple[float, float], p2: Tuple[float, float], x: float) -> Tuple[float, float]:
    x1, y1 = p1
    x2, y2 = p2
    if abs(x2 - x1) < 1e-15:
        return (x, y1)
    t = (x - x1) / (x2 - x1)
    y = y1 + t * (y2 - y1)
    return (x, y)


def intersect_segment_with_horizontal(p1: Tuple[float, float], p2: Tuple[float, float], y: float) -> Tuple[float, float]:
    x1, y1 = p1
    x2, y2 = p2
    if abs(y2 - y1) < 1e-15:
        return (x1, y)
    t = (y - y1) / (y2 - y1)
    x = x1 + t * (x2 - x1)
    return (x, y)


def clip_polygon_with_rect(subject: List[Tuple[float, float]], rect: Dict[str, float]) -> List[Tuple[float, float]]:
    def clip_edge(points: List[Tuple[float, float]], edge_type: str, value: float) -> List[Tuple[float, float]]:
        result: List[Tuple[float, float]] = []
        if not points:
            return result
        n = len(points)
        for i in range(n):
            p = points[i]
            q = points[(i + 1) % n]
            if edge_type == 'left':
                p_inside = p[0] >= value
                q_inside = q[0] >= value
                if p_inside and q_inside:
                    result.append(q)
                elif p_inside and not q_inside:
                    inter = intersect_segment_with_vertical(p, q, value)
                    result.append(inter)
                elif not p_inside and q_inside:
                    inter = intersect_segment_with_vertical(p, q, value)
                    result.append(inter)
                    result.append(q)
            elif edge_type == 'right':
                p_inside = p[0] <= value
                q_inside = q[0] <= value
                if p_inside and q_inside:
                    result.append(q)
                elif p_inside and not q_inside:
                    inter = intersect_segment_with_vertical(p, q, value)
                    result.append(inter)
                elif not p_inside and q_inside:
                    inter = intersect_segment_with_vertical(p, q, value)
                    result.append(inter)
                    result.append(q)
            elif edge_type == 'bottom':
                p_inside = p[1] >= value
                q_inside = q[1] >= value
                if p_inside and q_inside:
                    result.append(q)
                elif p_inside and not q_inside:
                    inter = intersect_segment_with_horizontal(p, q, value)
                    result.append(inter)
                elif not p_inside and q_inside:
                    inter = intersect_segment_with_horizontal(p, q, value)
                    result.append(inter)
                    result.append(q)
            elif edge_type == 'top':
                p_inside = p[1] <= value
                q_inside = q[1] <= value
                if p_inside and q_inside:
                    result.append(q)
                elif p_inside and not q_inside:
                    inter = intersect_segment_with_horizontal(p, q, value)
                    result.append(inter)
                elif not p_inside and q_inside:
                    inter = intersect_segment_with_horizontal(p, q, value)
                    result.append(inter)
                    result.append(q)
        return result

    clipped = subject[:]
    clipped = clip_edge(clipped, 'left', rect['min_lon'])
    clipped = clip_edge(clipped, 'right', rect['max_lon'])
    clipped = clip_edge(clipped, 'bottom', rect['min_lat'])
    clipped = clip_edge(clipped, 'top', rect['max_lat'])
    if len(clipped) >= 3:
        dedup: List[Tuple[float, float]] = []
        for pt in clipped:
            if not dedup or (abs(dedup[-1][0] - pt[0]) > 1e-12 or abs(dedup[-1][1] - pt[1]) > 1e-12):
                dedup.append(pt)
        if dedup and (abs(dedup[0][0] - dedup[-1][0]) < 1e-12 and abs(dedup[0][1] - dedup[-1][1]) < 1e-12):
            dedup = dedup[:-1]
        return dedup
    return []


def build_grid(min_lon: float, max_lon: float, min_lat: float, max_lat: float, rows: int, cols: int) -> List[Dict]:
    lon_step = (max_lon - min_lon) / cols
    lat_step = (max_lat - min_lat) / rows
    grid = []
    for r in range(rows):
        for c in range(cols):
            cell_min_lon = min_lon + c * lon_step
            cell_max_lon = min_lon + (c + 1) * lon_step
            cell_min_lat = min_lat + r * lat_step
            cell_max_lat = min_lat + (r + 1) * lat_step
            grid.append({
                'row': r + 1,
                'col': c + 1,
                'min_lon': cell_min_lon,
                'max_lon': cell_max_lon,
                'min_lat': cell_min_lat,
                'max_lat': cell_max_lat,
            })
    return grid


def write_kml(out_path: str, cells: List[Dict], clipped_polys: List[List[Tuple[float, float]]]):
    kml = ET.Element('kml', attrib={'xmlns': KML_NS})
    doc = ET.SubElement(kml, 'Document')
    style = ET.SubElement(doc, 'Style', attrib={'id': 'gridStyle'})
    line = ET.SubElement(style, 'LineStyle')
    ET.SubElement(line, 'color').text = 'ff2dc0fb'
    ET.SubElement(line, 'width').text = '3'
    poly_style = ET.SubElement(style, 'PolyStyle')
    ET.SubElement(poly_style, 'color').text = '40ffffff'

    for cell, poly in zip(cells, clipped_polys):
        if len(poly) < 3:
            continue
        placemark = ET.SubElement(doc, 'Placemark')
        ET.SubElement(placemark, 'name').text = f"r{cell['row']} c{cell['col']}"
        ET.SubElement(placemark, 'styleUrl').text = '#gridStyle'
        polygon = ET.SubElement(placemark, 'Polygon')
        outer = ET.SubElement(polygon, 'outerBoundaryIs')
        ring = ET.SubElement(outer, 'LinearRing')
        coords = ET.SubElement(ring, 'coordinates')
        coords_list = poly[:]
        if coords_list[0] != coords_list[-1]:
            coords_list.append(coords_list[0])
        coords.text = ' '.join([f"{lon},{lat},0" for lon, lat in coords_list])

    ET.ElementTree(kml).write(out_path, encoding='utf-8', xml_declaration=True)

# ---------------- GPX helpers ----------------

def point_in_polygon(lon: float, lat: float, poly: List[Tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n - 1):
        x1, y1 = poly[i]
        x2, y2 = poly[i + 1]
        intersects = ((y1 > lat) != (y2 > lat)) and (
            lon < (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-15) + x1
        )
        if intersects:
            inside = not inside
    return inside


def cell_for_point(lon: float, lat: float, grid: List[Dict]) -> Optional[Tuple[int, int]]:
    for cell in grid:
        lon_in = (lon >= cell['min_lon'] and (lon < cell['max_lon'] or abs(lon - cell['max_lon']) < 1e-12))
        lat_in = (lat >= cell['min_lat'] and (lat < cell['max_lat'] or abs(lat - cell['max_lat']) < 1e-12))
        if lon_in and lat_in:
            return (cell['row'], cell['col'])
    return None


def read_gpx(gpx_path: str) -> Dict:
    result: Dict = {'metadata': {}, 'metadata_elem': None, 'root': None, 'waypoints': []}
    try:
        tree = ET.parse(gpx_path)
        root = tree.getroot()
        result['root'] = root
        meta = root.find(f'{{{GPX_NS}}}metadata') or root.find('metadata')
        if meta is not None:
            result['metadata_elem'] = meta
            name_elem = meta.find(f'{{{GPX_NS}}}name') or meta.find('name')
            desc_elem = meta.find(f'{{{GPX_NS}}}desc') or meta.find('desc')
            author_elem = meta.find(f'{{{GPX_NS}}}author') or meta.find('author')
            link_elem = meta.find(f'{{{GPX_NS}}}link') or meta.find('link')
            time_elem = meta.find(f'{{{GPX_NS}}}time') or meta.find('time')
            result['metadata'] = {
                'name': name_elem.text if name_elem is not None else None,
                'desc': desc_elem.text if desc_elem is not None else None,
                'author': author_elem.find(f'{{{GPX_NS}}}name').text if (author_elem is not None and author_elem.find(f'{{{GPX_NS}}}name') is not None) else None,
                'link_href': link_elem.get('href') if link_elem is not None else None,
                'link_text': (link_elem.find(f'{{{GPX_NS}}}text').text if (link_elem is not None and link_elem.find(f'{{{GPX_NS}}}text') is not None) else None),
                'time': time_elem.text if time_elem is not None else None,
            }
        for wpt in root.findall(f'.//{{{GPX_NS}}}wpt') + root.findall('.//wpt'):
            lat = wpt.get('lat')
            lon = wpt.get('lon')
            if lat is None or lon is None:
                continue
            result['waypoints'].append({'elem': wpt, 'lat': float(lat), 'lon': float(lon)})
    except ET.ParseError:
        pass
    return result


def write_gpx(file_path: str, waypoints: List[Dict], title: str, source_meta: Optional[Dict] = None, source_name: Optional[str] = None, source_root: Optional[ET.Element] = None, source_metadata_elem: Optional[ET.Element] = None, cell_label: Optional[str] = None, count: Optional[int] = None, cell_bounds: Optional[Dict] = None, draw_rect: bool = False):
    version = '1.1'
    creator = 'GitHub Copilot'
    if source_root is not None:
        version = source_root.get('version') or version
        creator = source_root.get('creator') or creator

    gpx = ET.Element('gpx', attrib={
        'version': version,
        'creator': creator,
        'xmlns': GPX_NS
    })

    if source_metadata_elem is not None:
        meta_copy = copy.deepcopy(source_metadata_elem)
        def get_child(parent: ET.Element, local: str) -> Optional[ET.Element]:
            for ch in list(parent):
                tag = ch.tag
                if tag.endswith('}' + local) or tag == local:
                    return ch
            return None
        ns = None
        if '}' in meta_copy.tag:
            ns = meta_copy.tag.split('}')[0].strip('{')
        extra_desc = None
        if cell_label and count is not None:
            extra_desc = f"Cell {cell_label} · waypoints: {count}"
        if extra_desc:
            desc_elem = get_child(meta_copy, 'desc')
            if desc_elem is not None and (desc_elem.text or '').strip():
                desc_elem.text = f"{desc_elem.text}\n{extra_desc}"
            else:
                tag = f"{{{ns}}}desc" if ns else 'desc'
                desc_elem = ET.SubElement(meta_copy, tag)
                desc_elem.text = extra_desc
        if source_name:
            keywords = get_child(meta_copy, 'keywords')
            if keywords is None:
                tag = f"{{{ns}}}keywords" if ns else 'keywords'
                keywords = ET.SubElement(meta_copy, tag)
            if keywords.text:
                keywords.text = f"{keywords.text}, {source_name}"
            else:
                keywords.text = source_name
        gpx.append(meta_copy)
    else:
        metadata = ET.SubElement(gpx, 'metadata')
        ET.SubElement(metadata, 'name').text = title
        if source_meta:
            if source_meta.get('desc'):
                ET.SubElement(metadata, 'desc').text = source_meta['desc']
            if source_meta.get('author'):
                author = ET.SubElement(metadata, 'author')
                ET.SubElement(author, 'name').text = source_meta['author']
            if source_meta.get('link_href'):
                link = ET.SubElement(metadata, 'link', attrib={'href': source_meta['link_href']})
                if source_meta.get('link_text'):
                    ET.SubElement(link, 'text').text = source_meta['link_text']
            if source_meta.get('time'):
                ET.SubElement(metadata, 'time').text = source_meta['time']
        if source_name:
            ET.SubElement(metadata, 'keywords').text = source_name

    for wp in waypoints:
        wpt_elem = copy.deepcopy(wp['elem'])
        gpx.append(wpt_elem)

    if draw_rect and cell_bounds is not None:
        rte = ET.SubElement(gpx, f'{{{GPX_NS}}}rte')
        if title:
            name_tag = f'{{{GPX_NS}}}name'
            name_elem = ET.SubElement(rte, name_tag)
            name_elem.text = f"Bounds {cell_label}" if cell_label else 'Bounds'
        corners = [
            (cell_bounds['min_lat'], cell_bounds['min_lon']),
            (cell_bounds['min_lat'], cell_bounds['max_lon']),
            (cell_bounds['max_lat'], cell_bounds['max_lon']),
            (cell_bounds['max_lat'], cell_bounds['min_lon']),
            (cell_bounds['min_lat'], cell_bounds['min_lon']),
        ]
        for lat, lon in corners:
            ET.SubElement(rte, f'{{{GPX_NS}}}rtept', attrib={'lat': f'{lat}', 'lon': f'{lon}'})

    ET.ElementTree(gpx).write(file_path, encoding='utf-8', xml_declaration=True)

# ---------------- Unified main ----------------

def main():
    parser = argparse.ArgumentParser(description='Grid partition: generate KML grid and split GPX POIs per cell')
    parser.add_argument('--rows', type=int, default=5, help='Number of grid rows')
    parser.add_argument('--cols', type=int, default=2, help='Number of grid columns')
    parser.add_argument('--input-kml', type=str, default='Unbenannte Karte.kml', help='Input KML with polygon')
    parser.add_argument('--input-gpx', type=str, nargs='*', default=None, help='Specific GPX files to include (optional)')
    parser.add_argument('--emit-kml', action='store_true', help='Emit clipped grid KML')
    parser.add_argument('--emit-gpx', action='store_true', help='Emit per-cell GPX with waypoints')
    parser.add_argument('--out-kml', type=str, default='', help='Output KML path (optional)')
    parser.add_argument('--out-gpx-dir', type=str, default='', help='Output directory for GPX files (optional)')
    parser.add_argument('--draw-rect', action='store_true', help='Include rectangle route bounds in each GPX')
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    kml_path = args.input_kml if os.path.isabs(args.input_kml) else os.path.join(base_dir, args.input_kml)

    polygon = read_polygon_from_kml(kml_path)
    min_lon, max_lon, min_lat, max_lat = polygon_bbox(polygon)
    grid = build_grid(min_lon, max_lon, min_lat, max_lat, rows=args.rows, cols=args.cols)

    # KML output
    if args.emit_kml:
        out_kml = args.out_kml if args.out_kml else os.path.join(base_dir, f'grid-areas_{args.rows}x{args.cols}.kml')
        clipped = []
        for cell in grid:
            rect = {
                'min_lon': cell['min_lon'],
                'max_lon': cell['max_lon'],
                'min_lat': cell['min_lat'],
                'max_lat': cell['max_lat'],
            }
            inter = clip_polygon_with_rect(polygon, rect)
            clipped.append(inter)
        write_kml(out_kml, grid, clipped)
        print(f'KML written to {out_kml}')

    # GPX splitting
    if args.emit_gpx:
        candidate_gpx: List[str] = []
        if args.input_gpx:
            for path in args.input_gpx:
                candidate_gpx.append(path if os.path.isabs(path) else os.path.join(base_dir, path))
        else:
            camp = os.path.join(base_dir, 'CampWild Places.gpx')
            if os.path.exists(camp):
                candidate_gpx.append(camp)
            tet_dir = os.path.join(base_dir, 'TET')
            if os.path.isdir(tet_dir):
                for name in os.listdir(tet_dir):
                    if name.lower().endswith('.gpx'):
                        candidate_gpx.append(os.path.join(tet_dir, name))

        per_cell: Dict[Tuple[int, int], List[Dict]] = {}
        source_meta: Optional[Dict] = None
        source_name: Optional[str] = None
        source_root: Optional[ET.Element] = None
        source_metadata_elem: Optional[ET.Element] = None
        total_pois = 0
        for gpx_path in candidate_gpx:
            parsed = read_gpx(gpx_path)
            wps = parsed['waypoints']
            if source_meta is None:
                source_meta = parsed.get('metadata') or {}
            if source_name is None:
                source_name = os.path.basename(gpx_path)
            if source_root is None:
                source_root = parsed.get('root')
            if source_metadata_elem is None:
                source_metadata_elem = parsed.get('metadata_elem')
            for wp in wps:
                lon = wp['lon']
                lat = wp['lat']
                if not point_in_polygon(lon, lat, polygon):
                    continue
                rc = cell_for_point(lon, lat, grid)
                if rc is None:
                    continue
                per_cell.setdefault(rc, []).append(wp)
                total_pois += 1

        out_dir = args.out_gpx_dir if args.out_gpx_dir else os.path.join(base_dir, f'grid-pois-{args.rows}x{args.cols}')
        os.makedirs(out_dir, exist_ok=True)
        for cell in grid:
            rc = (cell['row'], cell['col'])
            wps = per_cell.get(rc, [])
            title = f"POIs r{cell['row']} c{cell['col']}"
            out_path = os.path.join(out_dir, f"pois_r{cell['row']}_c{cell['col']}.gpx")
            cell_label = f"r{cell['row']} c{cell['col']}"
            bounds = {
                'min_lon': cell['min_lon'],
                'max_lon': cell['max_lon'],
                'min_lat': cell['min_lat'],
                'max_lat': cell['max_lat'],
            }
            write_gpx(out_path, wps, title, source_meta=source_meta, source_name=source_name, source_root=source_root, source_metadata_elem=source_metadata_elem, cell_label=cell_label, count=len(wps), cell_bounds=bounds, draw_rect=args.draw_rect)
        print(f'Processed {len(candidate_gpx)} GPX files, found {total_pois} POIs in polygon.')
        print(f'Output written to {out_dir}')


if __name__ == '__main__':
    main()
