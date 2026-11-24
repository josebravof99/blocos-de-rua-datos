"""Aplicación local de lectura: mapa, filtros y exportaciones reproducibles."""
import argparse
import csv
import gzip
import io
import json
import math
import mimetypes
import os
import re
import sqlite3
import sys
import threading
import time
import unicodedata
import webbrowser
from collections import Counter, defaultdict
from datetime import date as calendar_date
from functools import partial, lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP / 'vendor_python'))
from preparar import DATA, DB, YEARS, RADIUS, PROJECT, UNPROJECT, OFFSETS, center, source_rows
import numpy as np

QUALITY = {'analisis': ['exacta', 'calle'], 'exacta': ['exacta'], 'calle': ['calle'],
           'centroide': ['centroide'], 'heredada': ['heredada'],
           'todas': ['exacta', 'calle', 'centroide', 'heredada']}

_LAYOUTS = {}

def layout(width):
    width = float(width)
    if width not in _LAYOUTS:
        radius = width / math.sqrt(3)
        step_y = 1.5 * radius
        offs = np.array([(radius * math.cos(math.radians(30 + 60 * i)),
                          radius * math.sin(math.radians(30 + 60 * i))) for i in range(6)])
        _LAYOUTS[width] = (radius, step_y, offs)
    return _LAYOUTS[width]


def available_widths():
    widths = [50] if DB.exists() else []
    for p in sorted(DB.parent.glob('mapa_*.sqlite')):
        try:
            w = int(p.stem.split('_')[1])
        except (IndexError, ValueError):
            continue
        if w not in widths:
            widths.append(w)
    return sorted(widths)


def db_for(width):
    width = int(width)
    return DB if width == 50 else DB.parent / f'mapa_{width}.sqlite'


def parse_width(params):
    try:
        width = int(params.get('width', 50))
    except (ValueError, TypeError):
        raise ValueError('Ancho de hexágono inválido')
    if width not in available_widths():
        raise ValueError('Ese ancho no tiene una base construida')
    return width


def connection(width=50):
    conn = sqlite3.connect(db_for(width).as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


_BUILDS = {}
_BUILD_LOCK = threading.Lock()
_EXPORT_SLOTS = threading.BoundedSemaphore(2)
STAGE_NAMES = {'inicio': 'Iniciando', 'grilla': 'Generando hexágonos', 'puntos': 'Guardando puntos',
    'indices': 'Creando índices', 'validacion': 'Validando', 'listo': 'Listo'}


def build_status(width):
    width = int(width)
    if width in available_widths() and width not in _BUILDS:
        return dict(width=width, status='done', stage='listo', done=1, total=1,
                    elapsed=0, eta=0, percent=100)
    st = _BUILDS.get(width)
    if st is None:
        raise ValueError('Ese ancho no está en generación')
    st = dict(st)
    if st['status'] == 'running':
        st['elapsed'] = round(time.time() - st['started'], 1)
    return st


def run_custom_build(width):
    width = int(width)
    with _BUILD_LOCK:
        if any(s['status'] == 'running' for s in _BUILDS.values()):
            raise ValueError('Ya hay una generación en curso; espera a que termine')
        st = _BUILDS.get(width)
        if st and st['status'] == 'running':
            return dict(st)
        st = dict(width=width, status='running', stage='inicio', done=0, total=1,
                  started=time.time(), elapsed=0, eta=None, percent=0, error=None)
        _BUILDS[width] = st
    def target():
        t0 = time.time()
        def prog(stage, done, total):
            el = time.time() - t0
            frac = min(done / max(total, 1), 1)
            st.update(stage=stage, done=done, total=total, elapsed=round(el, 1),
                      percent=round(frac * 100, 1),
                      eta=round(el / max(frac, 1e-6) * (1 - frac), 1) if frac > 0 else None)
        try:
            from preparar import build as build_grid
            build_grid(width, workers=min(8, os.cpu_count() or 1), progress=prog)
            st.update(status='done', stage='listo', done=1, total=1, percent=100,
                      elapsed=round(time.time() - t0, 1), eta=0)
        except Exception as e:
            print(f'Error generando {width} m: {e}', file=sys.stderr, flush=True)
            st.update(status='error', error=str(e), elapsed=round(time.time() - t0, 1))
    threading.Thread(target=target, daemon=True).start()
    return dict(st)


def folded(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.casefold())
                   if not unicodedata.combining(c))


def point_filter(params):
    where, args = [], []
    if params.get('year'):
        try:
            year = int(params['year'])
        except (ValueError, TypeError):
            raise ValueError('Año inválido')
        if year not in YEARS:
            raise ValueError('El año no tiene una base disponible')
        where.append('p.year=?')
        args.append(year)
    if params.get('date'):
        date = str(params['date']).strip()
        try:
            parsed_date = calendar_date.fromisoformat(date)
            if parsed_date.isoformat() != date:
                raise ValueError()
            year = parsed_date.year
        except (ValueError, TypeError):
            raise ValueError('Fecha inválida: usa AAAA-MM-DD')
        if params.get('year') and int(params['year']) != year:
            raise ValueError('La fecha no pertenece al año seleccionado')
        if year not in YEARS:
            raise ValueError('La fecha no tiene una base disponible')
        where.append('p.date=?')
        args.append(date)
    quality = params.get('quality', 'analisis')
    if quality not in QUALITY:
        raise ValueError('Filtro de precisión desconocido')
    where.append('p.quality IN (' + ','.join('?' for _ in QUALITY[quality]) + ')')
    args.extend(QUALITY[quality])
    for field in ['district', 'subprefecture']:
        if params.get(field):
            # Stable cell cohort is identical for points, counts and exports.
            where.append(f'h.{field}=?')
            args.append(params[field])
    return ' AND '.join(where), args


def selected_points(conn, params):
    where, args = point_filter(params)
    rows = [dict(r) for r in conn.execute('SELECT p.*,h.district AS cell_district,'
        'h.subprefecture AS cell_subprefecture,h.boundary AS cell_boundary '
        'FROM points p LEFT JOIN hexagons h ON h.id=p.hex_id WHERE ' + where + ' ORDER BY p.year,p.id', args)]
    search = folded(params.get('search', '').strip())
    if search:
        rows = [r for r in rows if search in folded(r['name'])]
    time_band = params.get('time', '')
    if time_band:
        if time_band not in {'madrugada', 'manana', 'tarde', 'noche', 'sin-hora'}:
            raise ValueError('Filtro de horario desconocido')
        details = source_details()
        def matches_time(row):
            value = details.get(row['id'], {}).get('parade_time', '').strip()
            match = re.match(r'^(\d{1,2}):([0-5]\d)', value)
            if not match:
                return time_band == 'sin-hora'
            hour = int(match.group(1))
            if time_band == 'sin-hora':
                return False
            return {'madrugada': 0 <= hour < 6, 'manana': 6 <= hour < 12,
                    'tarde': 12 <= hour < 18, 'noche': 18 <= hour < 24}[time_band]
        rows = [r for r in rows if matches_time(r)]
    return rows


@lru_cache(maxsize=1)
def source_details():
    details={}
    fields={'Hora de concentración':'concentration_time','Hora de desfile':'parade_time',
            'Hora de dispersión':'dispersal_time','Dirección de dispersión':'dispersal_address','Precio':'price'}
    for year, idx, row in source_rows():
        details[f'{year}-{idx:04d}'] = {out: row.get(key, '') for key, out in fields.items()}
    return details


def detailed_points(conn,params):
    extra=source_details()
    return [dict(p,**extra.get(p['id'],{})) for p in selected_points(conn,params)]


def cell_filter(params, prefix='h'):
    where, args = [], []
    for field in ['district', 'subprefecture']:
        if params.get(field):
            where.append(f'{prefix}.{field}=?')
            args.append(params[field])
    return (' AND '.join(where) or '1'), args


def cell_counts(rows):
    counts = defaultdict(Counter)
    for p in rows:
        if p['cell_district'] is not None:
            counts[(p['hex_id'], p['year'])][p['quality']] += 1
    return counts


def panel_rows(conn, params, years=None):
    """Resumen anual legado; la descarga principal usa daily_panel_rows."""
    years = YEARS if years is None else years
    params = dict(params)
    params.pop('year', None)
    rows = selected_points(conn, params)
    counts = cell_counts(rows)
    where, args = cell_filter(params)
    for h in conn.execute('SELECT * FROM hexagons h WHERE ' + where + ' ORDER BY h.r,h.q', args):
        lon, lat = UNPROJECT.transform(h['x'], h['y'])
        for year in years:
            c = counts.get((h['id'], year), {})
            n = sum(c.values())
            yield dict(hex_id=h['id'], anio=year, distrito=h['district'], subprefectura=h['subprefecture'],
                tratado=int(n > 0), n_ocurrencias=n, n_exactas=c.get('exacta',0), n_aprox_calle=c.get('calle',0),
                n_centroides=c.get('centroide',0), n_heredadas=c.get('heredada',0),
                longitud_centro=round(lon,8), latitud_centro=round(lat,8),
                celda_fronteriza=h['boundary'], area_en_municipio_m2=h['municipal_area'],
                precision_incluida=params.get('quality','analisis'),
                nombre_filtrado=params.get('search',''), fecha_filtrada=params.get('date',''),
                regla='punto_en_hexagono', limites='GeoSampa_2026-10-06')


def date_counts(conn, params):
    nodate = dict(params)
    nodate.pop('date', None)
    counts = Counter(r['date'] for r in selected_points(conn, nodate))
    clauses, args = (' WHERE year=?', [int(params['year'])]) if params.get('year') else ('', [])
    dates = [r[0] for r in conn.execute('SELECT DISTINCT date FROM points' + clauses + ' ORDER BY date', args)]
    return [dict(date=d, n=counts[d]) for d in dates]


def neighbor_ids(hex_id):
    """IDs de los seis vecinos por lado en la misma grilla, sin usar un buffer."""
    prefix, q, r = hex_id.rsplit('_', 2)
    q, r = int(q), int(r)
    return [f'{prefix}_{q+dq}_{r+dr}' for dq,dr in HEX_DIRS]


def daily_context(conn, params):
    # Los vecinos se evalúan en toda la ciudad para no cortar en fronteras
    # artificiales del distrito seleccionado. Precisión, fecha y nombre sí aplican.
    global_params = {k:v for k,v in params.items() if k not in ('district','subprefecture')}
    point_filter(global_params)
    rows = selected_points(conn, global_params)
    groups = defaultdict(list)
    for p in rows:
        if p['cell_district'] is not None:
            groups[(p['hex_id'],p['date'])].append(p)
    if params.get('date'):
        dates = [params['date']]
    else:
        clause,args = (' WHERE year=?',[int(params['year'])]) if params.get('year') else ('',[])
        dates = [r[0] for r in conn.execute('SELECT DISTINCT date FROM points'+clause+' ORDER BY date',args)]
    return dates,groups


def names_of(rows):
    names={}
    for p in rows:
        key=' '.join(folded(p['name']).split())
        names.setdefault(key,p['name'])
    return [names[k] for k in sorted(names)]


def compact_json(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'))


DAILY_FIELDS = ['hex_id','fecha','anio','ancho_m','distrito','subprefeitura','n_blocos','n_ocurrencias',
    'hay_bloco','blocos','ocurrencia_ids','horarios_concentracion','horarios_desfile','horarios_dispersion',
    'detalle_ocurrencias','adyacente_a_bloco','n_blocos_adyacentes','n_ocurrencias_adyacentes',
    'blocos_adyacentes','ocurrencia_ids_adyacentes','detalle_ocurrencias_adyacentes','hexagonos_adyacentes',
    'hexagonos_adyacentes_con_bloco','n_hexagonos_adyacentes','n_exactas','n_aprox_calle',
    'n_centroides','n_heredadas','longitud_centro','latitud_centro','celda_fronteriza',
    'area_en_municipio_m2','precision_incluida','nombre_filtrado','regla','limites']

def daily_panel_rows(conn, params):
    dates,groups=daily_context(conn,params)
    details=source_details()
    where,args=cell_filter(params)
    municipal_ids={r[0] for r in conn.execute('SELECT id FROM hexagons')}
    coverage=params.get('coverage','complete')
    if coverage not in ('complete','active'):
        raise ValueError('Cobertura de panel desconocida')
    width=int(params.get('width',50))
    candidates=set()
    if coverage=='active':
        for hid,day in groups:
            candidates.add(hid)
            candidates.update(neighbor_ids(hid))
    for h in conn.execute('SELECT * FROM hexagons h WHERE '+where+' ORDER BY h.r,h.q',args):
        if coverage=='active' and h['id'] not in candidates:
            continue
        neighbors=[hid for hid in neighbor_ids(h['id']) if hid in municipal_ids]
        lon,lat=UNPROJECT.transform(h['x'],h['y'])
        static=dict(hex_id=h['id'],ancho_m=width,distrito=h['district'],subprefectura=h['subprefecture'],
            hexagonos_adyacentes=compact_json(neighbors),n_hexagonos_adyacentes=len(neighbors),
            longitud_centro=round(lon,8),latitud_centro=round(lat,8),celda_fronteriza=h['boundary'],
            area_en_municipio_m2=h['municipal_area'],precision_incluida=params.get('quality','analisis'),
            nombre_filtrado=params.get('search',''),regla='punto_en_hexagono_y_vecinos_por_lado',limites='GeoSampa_2026-10-06')
        for day in dates:
            direct=groups.get((h['id'],day),[])
            adjacent=[p for hid in neighbors for p in groups.get((hid,day),[])]
            if coverage=='active' and not direct and not adjacent:
                continue
            quality_counts=Counter(p['quality'] for p in direct)
            names,adj_names=names_of(direct),names_of(adjacent)
            def event_detail(point, include_hex=False):
                source=details.get(point['id'],{})
                item=dict(ocurrencia_id=point['id'],bloco=point['name'],
                    hora_concentracion=source.get('concentration_time',''),
                    hora_desfile=source.get('parade_time',''),hora_dispersion=source.get('dispersal_time',''),
                    direccion=point.get('address',''),recorrido=point.get('route_text',''),
                    calidad=point['quality'],latitud=point['lat'],longitud=point['lon'],fuente=point.get('source',''))
                if include_hex:
                    item['hex_id']=point['hex_id']
                return item
            def schedule(points, time_key):
                return compact_json([dict(ocurrencia_id=p['id'],bloco=p['name'],hora=details.get(p['id'],{}).get(time_key,'')) for p in points])
            yield dict(static,fecha=day,anio=int(day[:4]),n_blocos=len(names),n_ocurrencias=len(direct),
                hay_bloco=int(bool(direct)),adyacente_a_bloco=int(bool(adjacent)),
                n_blocos_adyacentes=len(adj_names),n_ocurrencias_adyacentes=len(adjacent),
                blocos=compact_json(names),ocurrencia_ids=compact_json([p['id'] for p in direct]),
                horarios_concentracion=schedule(direct,'concentration_time'),
                horarios_desfile=schedule(direct,'parade_time'),horarios_dispersion=schedule(direct,'dispersal_time'),
                detalle_ocurrencias=compact_json([event_detail(p) for p in direct]),
                blocos_adyacentes=compact_json(adj_names),ocurrencia_ids_adyacentes=compact_json([p['id'] for p in adjacent]),
                detalle_ocurrencias_adyacentes=compact_json([event_detail(p,True) for p in adjacent]),
                hexagonos_adyacentes_con_bloco=compact_json([hid for hid in neighbors if (hid,day) in groups]),
                n_exactas=quality_counts['exacta'],n_aprox_calle=quality_counts['calle'],
                n_centroides=quality_counts['centroide'],n_heredadas=quality_counts['heredada'])


def summary(conn, params):
    rows = selected_points(conn, params)
    counts = cell_counts(rows)
    exposed = len({key[0] for key in counts})
    where, args = cell_filter(params)
    cells = conn.execute('SELECT count(*) FROM hexagons h WHERE ' + where, args).fetchone()[0]
    excluded_params = dict(params, quality='todas')
    total = len(selected_points(conn, excluded_params))
    by_year = {str(y): dict(points=sum(p['year']==y for p in rows),
                           treated=len({k[0] for k in counts if k[1]==y})) for y in YEARS}
    by_date = {d: dict(points=sum(p['date']==d for p in rows)) for d in sorted({p['date'] for p in rows})}
    return dict(points=len(rows), total_points=total, excluded=total-len(rows),
        treated=exposed, cells=cells, controls=cells-exposed,
        outside=sum(p['cell_district'] is None for p in rows),
        quality=dict(Counter(p['quality'] for p in rows)), by_year=by_year, by_date=by_date)


def hex_feature(h, counts=None, adjacent=False, width=50, details=None):
    _, step_y, offs = layout(width)
    x, y = float(width) * (h['q'] + h['r'] / 2), step_y * h['r']
    coords = [UNPROJECT.transform(x + dx, y + dy) for dx,dy in offs]
    coords.append(coords[0])
    c = counts or {}
    treated = int(sum(c.values()) > 0)
    props = dict(hex_id=h['id'], distrito=h['district'], subprefectura=h['subprefecture'],
        fronteriza=h['boundary'], area_municipal_m2=h['municipal_area'],
        n_ocurrencias=sum(c.values()), tratado=treated,
        adyacente=int(bool(adjacent) and not treated), precision=dict(c))
    props['ancho_m']=width
    if details:
        props.update(details)
    return dict(type='Feature', geometry=dict(type='Polygon', coordinates=[coords]), properties=props)


HEX_DIRS = [(1,0),(1,-1),(0,-1),(-1,0),(-1,1),(0,1)]

def adjacent_rows(conn, exposed_ids):
    """Las 6 celdas vecinas de cada celda con exposición (excluye las ya expuestas)."""
    wanted, seen = [], set(exposed_ids)
    for hid in exposed_ids:
        try:
            prefix, q, r = hid.rsplit('_', 2)
            q, r = int(q), int(r)
        except (ValueError, AttributeError):
            continue
        for dq, dr in HEX_DIRS:
            nid = f'{prefix}_{q+dq}_{r+dr}'
            if nid not in seen:
                seen.add(nid)
                wanted.append(nid)
    rows = []
    for i in range(0, len(wanted), 500):
        chunk = wanted[i:i+500]
        rows.extend(conn.execute('SELECT h.* FROM hexagons h WHERE h.id IN ('
            + ','.join('?' for _ in chunk) + ')', chunk).fetchall())
    return rows


def grid_view(conn, params, width=50):
    try:
        west,south,east,north = map(float, params['bbox'].split(','))
        if not all(math.isfinite(v) for v in [west,south,east,north]) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError()
    except (KeyError, ValueError):
        raise ValueError('Extensión de mapa inválida')
    corners = [PROJECT.transform(x,y) for x in [west,east] for y in [south,north]]
    xmin,xmax = min(x for x,y in corners),max(x for x,y in corners)
    ymin,ymax = min(y for x,y in corners),max(y for x,y in corners)
    where, args = cell_filter(params)
    where += ' AND b.xmax>=? AND b.xmin<=? AND b.ymax>=? AND b.ymin<=?'
    args.extend([xmin,xmax,ymin,ymax])
    global_params={k:v for k,v in params.items() if k not in ('district','subprefecture')}
    all_points=selected_points(conn, global_params)
    counts = cell_counts(all_points)
    by_cell=defaultdict(list)
    for p in all_points:
        if p['cell_district'] is not None:
            by_cell[p['hex_id']].append(p)
    counts_by_cell = defaultdict(Counter)
    for (hid, year), c in counts.items():
        counts_by_cell[hid].update(c)
    all_cells = params.get('controls','0') == '1'
    from_sql = ' FROM hexagons h JOIN hex_bounds b ON b.rowid=h.rowid WHERE ' + where
    if not all_cells:
        if not counts_by_cell:
            return dict(type='FeatureCollection', features=[], limited=False, mode='exposed')
        candidate_ids=set(counts_by_cell)
        if params.get('adjacent','0')=='1':
            for hid in counts_by_cell:
                candidate_ids.update(neighbor_ids(hid))
        from_sql += ' AND h.id IN (' + ','.join('?' for _ in candidate_ids) + ')'
        args.extend(candidate_ids)
    rows = conn.execute('SELECT h.*' + from_sql + ' LIMIT 12001', args).fetchall()
    if len(rows) > 12000:
        return dict(type='FeatureCollection', features=[], limited=True,
                    message=f'Acerca el mapa para ver la grilla de {width} metros.', mode='all')
    features=[]
    for h in rows:
        direct=by_cell.get(h['id'],[])
        neighbors=neighbor_ids(h['id'])
        near=[p for hid in neighbors for p in by_cell.get(hid,[])]
        details=dict(hay_bloco=int(bool(direct)),adyacente_a_bloco=int(bool(near)),
            n_blocos=len(names_of(direct)),n_blocos_adyacentes=len(names_of(near)),
            n_ocurrencias_adyacentes=len(near),blocos=names_of(direct),blocos_adyacentes=names_of(near),
            ocurrencia_ids=[p['id'] for p in direct],ocurrencia_ids_adyacentes=[p['id'] for p in near],
            hexagonos_adyacentes_con_bloco=[hid for hid in neighbors if hid in by_cell])
        features.append(hex_feature(h,counts_by_cell.get(h['id']),adjacent=bool(near),width=width,details=details))
    return dict(type='FeatureCollection', features=features,
                limited=False, mode='all' if all_cells else 'exposed')


def safe_csv_value(value):
    if isinstance(value,str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP / 'web'), **kwargs)

    timeout = 30

    def parse_request(self):
        if not super().parse_request():
            return False
        port = self.server.server_port
        hosts = {f'localhost:{port}', f'127.0.0.1:{port}'}
        if port == 80:
            hosts.update(('localhost', '127.0.0.1'))
        authorities = self.headers.get_all('Host', [])
        if len(authorities) != 1 or authorities[0].lower() not in hosts:
            self.send_error(403, 'Host local requerido')
            return False
        origin = 'http://' + authorities[0].lower()
        origins = self.headers.get_all('Origin', [])
        if ((origins and origins != [origin])
                or self.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site')):
            self.send_error(403, 'Origen no permitido')
            return False
        return True

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy',
                         "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data: https://*.tile.openstreetmap.org; "
                         "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        super().end_headers()

    def log_message(self, format, *args):
        if args and str(args[0]).startswith('GET /api/hexagons'):
            return
        super().log_message(format, *args)

    def json_response(self, value, status=200):
        content = json.dumps(value, ensure_ascii=False, separators=(',',':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = {k:v[-1] for k,v in parse_qs(parsed.query).items()}
        if not parsed.path.startswith('/api/'):
            return super().do_GET()
        conn = None
        exporting = parsed.path.startswith('/api/export/')
        if exporting and not _EXPORT_SLOTS.acquire(blocking=False):
            return self.json_response({'error':'Hay dos descargas en curso. Intenta de nuevo al terminar.'}, 429)
        try:
            path = parsed.path
            if path == '/api/builds':
                if not params.get('width'):
                    raise ValueError('Indica el ancho a consultar')
                try:
                    w = int(params['width'])
                except (ValueError, TypeError):
                    raise ValueError('Ancho inválido')
                return self.json_response(build_status(w))
            width = parse_width(params)
            conn = connection(width)
            if path == '/api/meta':
                meta = json.loads(conn.execute("SELECT value FROM metadata WHERE key='application'").fetchone()[0])
                meta['width'] = width
                meta['widths'] = available_widths()
                return self.json_response(meta)
            if path == '/api/points':
                return self.json_response(detailed_points(conn, params))
            if path == '/api/dates':
                point_filter(params)
                return self.json_response(date_counts(conn, params))
            if path == '/api/summary':
                return self.json_response(summary(conn, params))
            if path == '/api/hexagons':
                return self.json_response(grid_view(conn, params, width))
            if path == '/api/boundaries':
                which = 'subprefecturas' if params.get('level')=='subprefecture' else 'distritos'
                return self.json_response(json.loads((DATA / (which+'.geojson')).read_text(encoding='utf-8')))
            if path == '/api/routes':
                file = APP / 'auditoria' / 'rutas_2026.geojson'
                return self.json_response(json.loads(file.read_text(encoding='utf-8')) if file.exists()
                    else {'type':'FeatureCollection','features':[]})
            if path == '/api/review':
                file = APP.parent / 'docs' / 'revision_material.md'
                content = file.read_bytes() if file.exists() else 'Revisión de materiales en preparación.'.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type','text/plain; charset=utf-8')
                self.send_header('Content-Length',str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            if path == '/api/export/points':
                rows = detailed_points(conn,params)
                fields = [r[1] for r in conn.execute('PRAGMA table_info(points)')] + ['cell_district','cell_subprefecture','cell_boundary',
                    'concentration_time','parade_time','dispersal_time','dispersal_address','price']
                return self.csv_download(rows,fields,f'puntos_blocos_{width}m.csv',compressed=False)
            if path == '/api/export/adjacency':
                where,args=cell_filter(params)
                municipal_ids={r[0] for r in conn.execute('SELECT id FROM hexagons')}
                rows=(dict(hex_id=h[0],hex_id_adyacente=nid,ancho_m=width)
                    for h in conn.execute('SELECT h.id FROM hexagons h WHERE '+where+' ORDER BY h.r,h.q',args)
                    for nid in neighbor_ids(h[0]) if nid in municipal_ids)
                return self.csv_download(rows,['hex_id','hex_id_adyacente','ancho_m'],f'adyacencias_{width}m.csv.gz',compressed=True)
            if path == '/api/export/panel':
                point_filter(params)
                export_params=dict(params)
                if params.get('scope')=='all' and not params.get('date'):
                    export_params.pop('year',None)
                if export_params.get('coverage','complete') not in ('complete','active'):
                    raise ValueError('Cobertura de panel desconocida')
                rows = daily_panel_rows(conn,export_params)
                suffix='_con_blocos_o_vecinos' if export_params.get('coverage')=='active' else '_completo'
                period = export_params.get('date', '').strip() or (
                    str(int(export_params['year'])) if export_params.get('year') else 'todos_los_anios')
                return self.csv_download(rows,DAILY_FIELDS,f'panel_fecha_{period}_{width}m{suffix}.csv',compressed=False)
            if path == '/api/export/grid':
                point_filter(params)
                return self.geojson_download(conn, params, width)
            self.json_response({'error':'Ruta no encontrada'},404)
        except (ValueError,KeyError) as e:
            self.json_response({'error':str(e)},400)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            print(f'Error: {e}',file=sys.stderr,flush=True)
            self.json_response({'error':'Error al consultar la base local'},500)
        finally:
            if conn is not None:
                conn.close()
            if exporting:
                _EXPORT_SLOTS.release()

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path != '/api/builds':
                return self.json_response({'error':'Ruta no encontrada'},404)
            if self.headers.get_content_type() != 'application/json':
                return self.json_response({'error':'Se requiere JSON'}, 415)
            lengths = self.headers.get_all('Content-Length', [])
            if (self.headers.get('Transfer-Encoding') is not None or len(lengths) != 1
                    or not re.fullmatch(r'[0-9]{1,10}', lengths[0])):
                raise ValueError('Longitud de solicitud inválida')
            length = int(lengths[0])
            if length > 1024:
                return self.json_response({'error':'Solicitud demasiado grande'}, 413)
            try:
                body = json.loads(self.rfile.read(length).decode('utf-8'))
            except (ValueError, RecursionError):
                raise ValueError('Pedido inválido')
            width = body.get('width') if isinstance(body, dict) else None
            if type(width) is not int:
                raise ValueError('Indica el ancho en metros como número entero')
            if width <= 100:
                raise ValueError('El valor propio debe ser mayor a 100 m (25 y 50 ya existen)')
            if width > 2000:
                raise ValueError('El máximo es 2000 m')
            if width in available_widths():
                return self.json_response(dict(build_status(width), exists=True))
            return self.json_response(run_custom_build(width))
        except (ValueError,KeyError) as e:
            self.json_response({'error':str(e)},400)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            print(f'Error: {e}',file=sys.stderr,flush=True)
            self.json_response({'error':'Error al consultar la base local'},500)

    def download_headers(self,filename,content_type):
        self.send_response(200)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.send_header('Connection','close')
        self.end_headers()
        self.close_connection = True

    def csv_download(self,rows,fields,filename,compressed):
        self.download_headers(filename,'application/gzip' if compressed else 'text/csv; charset=utf-8')
        raw = gzip.GzipFile(filename='',mode='wb',fileobj=self.wfile,mtime=0) if compressed else self.wfile
        try:
            raw.write(b'\xef\xbb\xbf')
            buffer = io.StringIO(newline='')
            writer = csv.DictWriter(buffer,fieldnames=fields,extrasaction='ignore')
            writer.writeheader()
            for idx,row in enumerate(rows):
                writer.writerow({k:safe_csv_value(v) for k,v in row.items()})
                if idx % 1000 == 999:
                    raw.write(buffer.getvalue().encode('utf-8'))
                    buffer.seek(0)
                    buffer.truncate(0)
            raw.write(buffer.getvalue().encode('utf-8'))
        finally:
            if compressed:
                raw.close()

    def geojson_download(self,conn,params,width):
        self.download_headers(f'grilla_{width}m.geojson.gz','application/gzip')
        global_params={k:v for k,v in params.items() if k not in ('district','subprefecture')}
        all_points=selected_points(conn,global_params)
        counts = cell_counts(all_points)
        by_cell=defaultdict(list)
        for p in all_points:
            if p['cell_district'] is not None:
                by_cell[p['hex_id']].append(p)
        municipal_ids={r[0] for r in conn.execute('SELECT id FROM hexagons')}
        merged = defaultdict(Counter)
        for (hid,year),c in counts.items():
            merged[hid].update(c)
        where,args = cell_filter(params)
        with gzip.GzipFile(filename='',mode='wb',fileobj=self.wfile,mtime=0) as stream:
            stream.write(b'{"type":"FeatureCollection","features":[')
            first=True
            for h in conn.execute('SELECT * FROM hexagons h WHERE '+where+' ORDER BY r,q',args):
                if not first:
                    stream.write(b',')
                first=False
                feature = hex_feature(h,merged.get(h['id']),width=width)
                direct=by_cell.get(h['id'],[])
                neighbors=[hid for hid in neighbor_ids(h['id']) if hid in municipal_ids]
                near=[p for hid in neighbors for p in by_cell.get(hid,[])]
                feature['properties'].pop('tratado',None)
                feature['properties'].pop('adyacente',None)
                feature['properties'].update(anio=params.get('year','todos'), precision_incluida=params.get('quality','analisis'),
                    nombre_filtrado=params.get('search',''), fecha_filtrada=params.get('date',''),
                    regla='punto_en_hexagono', limites='GeoSampa_2026-10-06',
                    ancho_m=width, crs_medicion='EPSG:31983',hexagonos_adyacentes=neighbors,
                    hay_bloco=int(bool(direct)),adyacente_a_bloco=int(bool(near)),
                    n_blocos=len(names_of(direct)),n_blocos_adyacentes=len(names_of(near)),
                    n_ocurrencias_adyacentes=len(near),blocos=names_of(direct),
                    ocurrencia_ids=[p['id'] for p in direct])
                stream.write(json.dumps(feature,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
            stream.write(b']}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--open',action='store_true')
    args = parser.parse_args()
    if not DB.exists():
        raise SystemExit('Falta la base. Ejecuta preparar.py antes de iniciar.')
    server = ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Mapa disponible en http://127.0.0.1:{args.port}',flush=True)
    if args.open:
        webbrowser.open(f'http://127.0.0.1:{args.port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
