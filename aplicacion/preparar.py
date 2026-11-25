"""Prepara una grilla métrica reproducible y puntos sin modificar fuentes."""
import argparse
import csv
import hashlib
import json
import math
import os
import sqlite3
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP / 'vendor_python'))
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Point, Polygon, shape, mapping
from shapely.ops import transform, unary_union

WIDTH = 50.0
RADIUS = WIDTH / math.sqrt(3)
STEP_Y = 1.5 * RADIUS
FULL_AREA = WIDTH * WIDTH * math.sqrt(3) / 2
WIDTHS = [25, 50, 100, 200, 500]
PROJECT = Transformer.from_crs(4326, 31983, always_xy=True)
UNPROJECT = Transformer.from_crs(31983, 4326, always_xy=True)
DATA = APP / 'datos'
DB = DATA / 'v1.0.3' / 'mapa.sqlite'
YEARS = [2018, 2019, 2020, 2023, 2024, 2025, 2026]
OFFSETS = np.array([(RADIUS * math.cos(math.radians(30 + 60 * i)),
                     RADIUS * math.sin(math.radians(30 + 60 * i))) for i in range(6)])


def set_width(width):
    """Fija el ancho entre lados opuestos (m) para esta construcción."""
    global WIDTH, RADIUS, STEP_Y, FULL_AREA, OFFSETS
    WIDTH = float(width)
    RADIUS = WIDTH / math.sqrt(3)
    STEP_Y = 1.5 * RADIUS
    FULL_AREA = WIDTH * WIDTH * math.sqrt(3) / 2
    OFFSETS = np.array([(RADIUS * math.cos(math.radians(30 + 60 * i)),
                         RADIUS * math.sin(math.radians(30 + 60 * i))) for i in range(6)])


def db_for(width):
    width = int(width)
    return DB.parent / ('mapa.sqlite' if width == 50 else f'mapa_{width}.sqlite')


def hex_name(q, r):
    return f'H{WIDTH:g}_{int(q)}_{int(r)}'


def center(q, r):
    return WIDTH * (q + r / 2), STEP_Y * r


def hexagon(q, r):
    return Polygon(OFFSETS + np.array(center(q, r)))


def axial(x, y):
    """Cube rounding gives a unique cell, including deterministic boundary ties."""
    fr = y / STEP_Y
    fq = x / WIDTH - fr / 2
    fs = -fq - fr
    q, r, s = round(fq), round(fr), round(fs)
    dq, dr, ds = abs(q - fq), abs(r - fr), abs(s - fs)
    if dq > dr and dq > ds:
        q = -r - s
    elif dr > ds:
        r = -q - s
    return int(q), int(r)


def quality(value):
    value = value.lower()
    if value.startswith('exacta'):
        return 'exacta'
    if 'centroide' in value:
        return 'centroide'
    if 'heredada' in value:
        return 'heredada'
    if any(t in value for t in ('calle', 'dirección', 'recorrido')):
        return 'calle'
    raise ValueError(f'Clase de georreferenciación desconocida: {value}')


def source_rows():
    counters = Counter()
    with (APP.parent / 'datos' / 'blocos.csv').open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            year = int(row['Año'])
            counters[year] += 1
            yield year, counters[year], row


def read_points():
    records = []
    for year, idx, row in source_rows():
        lat, lon = float(row['Latitud']), float(row['Longitud'])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f'Coordenadas inválidas: {year}, fila {idx}')
        x, y = PROJECT.transform(lon, lat)
        q, r = axial(x, y)
        records.append(dict(id=f'{year}-{idx:04d}', year=year, name=row['Nombre del bloco'],
            date=row['Fecha'], lat=lat, lon=lon, x=x, y=y, q=q, r=r, hex_id=hex_name(q, r),
            quality=quality(row['Clase de georreferenciación']), district='', subprefecture='',
            address=row['Dirección de concentración'], route_text=row['Recorrido / calles'],
            source=row['Referencia directa'], source_id=row['ID de fuente'],
            source_record_id=row['ID en fuente'], original_zone=row['Región / zona'],
            original_neighborhood=row['Barrio'], precision=row['Método / precisión'],
            status=row['Estado de verificación'], notes=row['Observaciones / límites']))
    return records


def geography():
    districts = json.loads((DATA / 'distritos.geojson').read_text(encoding='utf-8'))
    subs = json.loads((DATA / 'subprefecturas.geojson').read_text(encoding='utf-8'))
    subnames = {int(f['properties']['cd_identificador_subprefeitura']):
                f['properties']['nm_subprefeitura'].title() for f in subs['features']}
    items = []
    for f in districts['features']:
        p = f['properties']
        geom = shapely.make_valid(transform(PROJECT.transform, shape(f['geometry'])))
        items.append(dict(id=str(p['cd_distrito_municipal']), name=p['nm_distrito_municipal'].title(),
                          subprefecture=subnames[int(p['cd_identificador_subprefeitura'])], geometry=geom))
    items.sort(key=lambda d: d['id'])
    return items, unary_union([d['geometry'] for d in items]), districts, subs


def assign_points(points, districts):
    tree = shapely.STRtree([d['geometry'] for d in districts])
    for row in points:
        point = Point(row['x'], row['y'])
        matches = sorted(int(i) for i in tree.query(point) if districts[int(i)]['geometry'].covers(point))
        if matches:
            d = districts[matches[0]]
            row['district'], row['subprefecture'] = d['name'], d['subprefecture']


_districts = None
_municipality = None
_tree = None


def worker_init(districts_wkb, municipality_wkb, width):
    global _districts, _municipality, _tree
    set_width(width)
    _districts = [dict(id=d['id'], name=d['name'], subprefecture=d['subprefecture'],
                       geometry=shapely.from_wkb(d['wkb'])) for d in districts_wkb]
    _municipality = shapely.from_wkb(municipality_wkb)
    _tree = shapely.STRtree([d['geometry'] for d in _districts])
    shapely.prepare(_municipality)


def grid_chunk(task):
    rstart, rend, bounds = task
    xmin, ymin, xmax, ymax = bounds
    qs, rs = [], []
    for r in range(rstart, rend):
        qmin = math.floor((xmin - WIDTH) / WIDTH - r / 2)
        qmax = math.ceil((xmax + WIDTH) / WIDTH - r / 2)
        qrow = np.arange(qmin, qmax + 1, dtype=np.int32)
        qs.append(qrow)
        rs.append(np.full(len(qrow), r, dtype=np.int32))
    q, r = np.concatenate(qs), np.concatenate(rs)
    x, y = WIDTH * (q + r / 2), STEP_Y * r
    centers = np.column_stack([x, y])
    polygons = shapely.polygons(centers[:, None, :] + OFFSETS[None, :, :])
    keep = shapely.intersects(polygons, _municipality)
    q, r, x, y, polygons = (v[keep] for v in (q, r, x, y, polygons))
    hits = _tree.query(polygons, predicate='intersects')
    # Interior cells intersect one district; boundary cells use largest overlap.
    assignments = np.full(len(q), -1, dtype=np.int32)
    areas = np.zeros(len(q))
    edges = np.zeros(len(q), dtype=np.int8)
    candidate_counts = np.bincount(hits[0], minlength=len(q))
    for di, d in enumerate(_districts):
        idx = hits[0][hits[1] == di]
        if len(idx) == 0:
            continue
        contained = shapely.covers(d['geometry'], polygons[idx])
        overlap = np.full(len(idx), FULL_AREA)
        overlap[~contained] = shapely.area(shapely.intersection(polygons[idx[~contained]], d['geometry']))
        improve = overlap > areas[idx]
        assignments[idx[improve]] = di
        areas[idx[improve]] = overlap[improve]
        edges[idx[~contained]] = 1
    partial = ~shapely.covers(_municipality, polygons)
    municipal_area = np.full(len(q), FULL_AREA)
    municipal_area[partial] = shapely.area(shapely.intersection(polygons[partial], _municipality))
    records = []
    for i in range(len(q)):
        # Exclude zero-area contacts with municipal boundary.
        if assignments[i] < 0 or municipal_area[i] < 1e-8:
            continue
        d = _districts[int(assignments[i])]
        records.append((hex_name(q[i], r[i]), int(q[i]), int(r[i]), float(x[i]), float(y[i]),
                        d['name'], d['subprefecture'], int(edges[i] or candidate_counts[i] > 1),
                        round(float(municipal_area[i]), 6)))
    return records


def build(width=50, workers=8, progress=None):
    width = int(width)
    if width not in WIDTHS and width <= 100:
        raise ValueError(f'Ancho no soportado: {width}. Usa uno de {WIDTHS} o un valor propio mayor a 100')
    def report(stage, done, total):
        if progress:
            progress(stage, done, total)
    set_width(width)
    target = db_for(width)
    DB.parent.mkdir(parents=True, exist_ok=True)
    districts, municipality, district_json, sub_json = geography()
    points = read_points()
    assign_points(points, districts)
    temporary = target.with_suffix('.nuevo.sqlite')
    if temporary.exists():
        temporary.unlink()
    conn = sqlite3.connect(temporary)
    conn.executescript('''
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
        CREATE TABLE hexagons (id TEXT PRIMARY KEY, q INTEGER, r INTEGER, x REAL, y REAL,
          district TEXT, subprefecture TEXT, boundary INTEGER, municipal_area REAL);
        CREATE VIRTUAL TABLE hex_bounds USING rtree(rowid, xmin, xmax, ymin, ymax);
        CREATE TABLE points (id TEXT PRIMARY KEY, year INTEGER, name TEXT, date TEXT, lat REAL, lon REAL,
          x REAL, y REAL, q INTEGER, r INTEGER, hex_id TEXT, quality TEXT, district TEXT,
          subprefecture TEXT, address TEXT, route_text TEXT, source TEXT, source_id TEXT,
          source_record_id TEXT, original_zone TEXT, original_neighborhood TEXT, precision TEXT,
          status TEXT, notes TEXT);
        CREATE TABLE counts (hex_id TEXT, year INTEGER, quality TEXT, n INTEGER,
          PRIMARY KEY(hex_id, year, quality));
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
    ''')
    bounds = municipality.bounds
    rmin = math.floor((bounds[1] - RADIUS) / STEP_Y)
    rmax = math.ceil((bounds[3] + RADIUS) / STEP_Y)
    tasks = [(r, min(r + 40, rmax + 1), bounds) for r in range(rmin, rmax + 1, 40)]
    district_payload = [dict(id=d['id'], name=d['name'], subprefecture=d['subprefecture'],
                             wkb=d['geometry'].wkb) for d in districts]
    workers = min(max(workers, 1), os.cpu_count() or 1, 8)
    print(f'Preparando grilla: {workers} procesos, {len(tasks)} lotes', flush=True)
    with ProcessPoolExecutor(max_workers=workers, initializer=worker_init,
                             initargs=(district_payload, municipality.wkb, width)) as pool:
        for idx, rows in enumerate(pool.map(grid_chunk, tasks), 1):
            conn.executemany('INSERT INTO hexagons VALUES (?,?,?,?,?,?,?,?,?)', rows)
            report('grilla', idx, len(tasks))
            if idx % 10 == 0 or idx == len(tasks):
                print(f'Lotes {idx}/{len(tasks)}; {conn.execute("SELECT count(*) FROM hexagons").fetchone()[0]:,} celdas', flush=True)
    report('puntos', 1, 2)
    conn.execute('INSERT INTO hex_bounds SELECT rowid,x-?,x+?,y-?,y+? FROM hexagons', (WIDTH / 2, WIDTH / 2, RADIUS, RADIUS))
    fields = list(points[0])
    conn.executemany('INSERT INTO points VALUES (' + ','.join('?' for _ in fields) + ')',
                     [tuple(p[f] for f in fields) for p in points])
    conn.execute('INSERT INTO counts SELECT hex_id,year,quality,count(*) FROM points '
                 'WHERE district<>\'\' GROUP BY hex_id,year,quality')
    report('puntos', 2, 2)
    conn.executescript('''
        CREATE INDEX hex_district ON hexagons(district);
        CREATE INDEX hex_sub ON hexagons(subprefecture);
        CREATE INDEX point_year ON points(year);
        CREATE INDEX point_hex ON points(hex_id,year,quality);
        CREATE INDEX point_district ON points(district,subprefecture);
        CREATE INDEX counts_year ON counts(year,quality,hex_id);
    ''')
    report('indices', 1, 1)
    missing = conn.execute("SELECT count(*) FROM points p LEFT JOIN hexagons h ON h.id=p.hex_id WHERE p.district<>'' AND h.id IS NULL").fetchone()[0]
    if missing:
        raise ValueError(f'{missing} puntos municipales sin celda')
    files = [DATA / 'distritos.geojson', DATA / 'subprefecturas.geojson']
    metadata = dict(years=YEARS, total_points=len(points), total_hexagons=conn.execute('SELECT count(*) FROM hexagons').fetchone()[0],
        width_m=WIDTH, side_m=RADIUS, area_m2=FULL_AREA, crs='EPSG:31983',
        workers=workers, prepared_at=datetime.now(timezone.utc).isoformat(), boundary_snapshot='2026-10-06',
        boundary_rule='Mayor área de intersección con distrito; IDs axiales con origen UTM (0,0)',
        outside_points=sum(not p['district'] for p in points), quality_counts=dict(Counter(p['quality'] for p in points)),
        districts=[{k:v for k,v in d.items() if k!='geometry'} for d in districts],
        boundary_sources=[dict(file=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            url='https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs',
            layer='geoportal:distrito_municipal' if p.name=='distritos.geojson' else 'geoportal:subprefeitura') for p in files])
    conn.execute('INSERT INTO metadata VALUES (?,?)', ('application', json.dumps(metadata, ensure_ascii=False)))
    conn.commit()
    # Una grilla nueva también entrega un panel diario consultable con ceros.
    from actualizar_paneles import install_daily_panel
    conn.row_factory = sqlite3.Row
    install_daily_panel(conn,width)
    checks = dict(point_count=conn.execute('SELECT count(*) FROM points').fetchone()[0],
        unique_hexagons=metadata['total_hexagons'], points_in_city=len(points)-metadata['outside_points'],
        outside_points=metadata['outside_points'], points_without_hexagon=missing,
        count_sum=conn.execute('SELECT sum(n) FROM counts').fetchone()[0],
        municipal_area_m2=municipality.area,
        sum_hex_municipal_area_m2=conn.execute('SELECT sum(municipal_area) FROM hexagons').fetchone()[0],
        integrity=conn.execute('PRAGMA integrity_check').fetchone()[0])
    assert checks['point_count'] == 4109
    assert checks['count_sum'] == checks['points_in_city']
    # municipal_area se guarda con 6 decimales: tolerancia proporcional al nº de celdas.
    assert abs(checks['municipal_area_m2'] - checks['sum_hex_municipal_area_m2']) < max(1.0, metadata['total_hexagons'] * 1e-6)
    assert checks['integrity'] == 'ok'
    conn.close()
    report('validacion', 1, 1)
    for attempt in range(10):
        try:
            temporary.replace(target)
            break
        except OSError:
            if attempt == 9:
                raise
            time.sleep(1)
    (DATA / f'validacion_{width}.json').write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding='utf-8')
    (DATA / f'metadatos_{width}.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
    if width == 50:
        (DATA / 'validacion.json').write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding='utf-8')
        (DATA / 'metadatos.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf-8')
    report('listo', 1, 1)
    print(json.dumps(checks, indent=2, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--width', type=int, default=50)
    args = parser.parse_args()
    build(args.width, args.workers)
