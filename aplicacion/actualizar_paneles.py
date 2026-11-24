"""Agrega el panel diario a las bases existentes sin regenerar las grillas."""
import argparse
import json
import sqlite3
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import servidor as s


def install_daily_panel(conn,width):
    width=int(width)
    dates,groups=s.daily_context(conn,{'quality':'analisis'})
    with conn:
        conn.execute('CREATE TABLE IF NOT EXISTS panel_fechas(fecha TEXT PRIMARY KEY, anio INTEGER)')
        conn.execute('CREATE TABLE IF NOT EXISTS panel_direcciones(dq INTEGER,dr INTEGER,PRIMARY KEY(dq,dr))')
        conn.execute('''CREATE TABLE IF NOT EXISTS panel_conteos_fecha(
          hex_id TEXT,fecha TEXT,n_blocos INTEGER,n_ocurrencias INTEGER,blocos TEXT,ocurrencia_ids TEXT,
          n_exactas INTEGER,n_aprox_calle INTEGER,PRIMARY KEY(hex_id,fecha))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS panel_nombres_fecha(
          hex_id TEXT,fecha TEXT,nombre_clave TEXT,PRIMARY KEY(hex_id,fecha,nombre_clave))''')
        for table in ['panel_fechas','panel_direcciones','panel_conteos_fecha','panel_nombres_fecha']:
            conn.execute('DELETE FROM '+table)
        conn.executemany('INSERT INTO panel_fechas VALUES (?,?)',[(d,int(d[:4])) for d in dates])
        conn.executemany('INSERT INTO panel_direcciones VALUES (?,?)',s.HEX_DIRS)
        counts,names=[],[]
        for (hid,day),rows in groups.items():
            blocos=s.names_of(rows)
            quality=Counter(p['quality'] for p in rows)
            counts.append((hid,day,len(blocos),len(rows),s.compact_json(blocos),
                           s.compact_json([p['id'] for p in rows]),quality['exacta'],quality['calle']))
            names.extend((hid,day,' '.join(s.folded(name).split())) for name in blocos)
        conn.executemany('INSERT INTO panel_conteos_fecha VALUES (?,?,?,?,?,?,?,?)',counts)
        conn.executemany('INSERT INTO panel_nombres_fecha VALUES (?,?,?)',names)
        for view in ['panel_fecha','panel_vecinos']:
            conn.execute('DROP VIEW IF EXISTS '+view)
        nid=f"('H{width}_'||(h.q+d.dq)||'_'||(h.r+d.dr))"
        conn.execute(f'''CREATE VIEW panel_vecinos AS SELECT h.id AS hex_id,n.id AS hex_id_adyacente,
            {width} AS ancho_m FROM hexagons h CROSS JOIN panel_direcciones d
            JOIN hexagons n ON n.id={nid}''')
        conn.execute(f'''CREATE VIEW panel_fecha AS
            SELECT h.id AS hex_id,f.fecha,f.anio,{width} AS ancho_m,
              h.district AS distrito,h.subprefecture AS subprefectura,
              COALESCE(c.n_blocos,0) AS n_blocos,COALESCE(c.n_ocurrencias,0) AS n_ocurrencias,
              CAST(COALESCE(c.n_ocurrencias,0)>0 AS INTEGER) AS hay_bloco,
              CAST(EXISTS(SELECT 1 FROM panel_direcciones d JOIN panel_conteos_fecha nc
                ON nc.hex_id={nid} AND nc.fecha=f.fecha) AS INTEGER) AS adyacente_a_bloco,
              (SELECT count(DISTINCT nn.nombre_clave) FROM panel_direcciones d JOIN panel_nombres_fecha nn
                ON nn.hex_id={nid} AND nn.fecha=f.fecha) AS n_blocos_adyacentes,
              COALESCE((SELECT sum(nc.n_ocurrencias) FROM panel_direcciones d JOIN panel_conteos_fecha nc
                ON nc.hex_id={nid} AND nc.fecha=f.fecha),0) AS n_ocurrencias_adyacentes,
              COALESCE(c.blocos,'[]') AS blocos,COALESCE(c.ocurrencia_ids,'[]') AS ocurrencia_ids,
              COALESCE(c.n_exactas,0) AS n_exactas,COALESCE(c.n_aprox_calle,0) AS n_aprox_calle,
              h.boundary AS celda_fronteriza,h.municipal_area AS area_en_municipio_m2,
              'analisis' AS precision_incluida
            FROM hexagons h CROSS JOIN panel_fechas f LEFT JOIN panel_conteos_fecha c
            ON c.hex_id=h.id AND c.fecha=f.fecha''')
    return dict(width=width,dates=len(dates),cells=conn.execute('SELECT count(*) FROM hexagons').fetchone()[0],
        occupied_cell_dates=len(counts),occurrences=sum(r[3] for r in counts),
        complete_rows=len(dates)*conn.execute('SELECT count(*) FROM hexagons').fetchone()[0])


def update_width(width):
    conn=sqlite3.connect(s.db_for(width),timeout=60)
    conn.row_factory=sqlite3.Row
    try:
        result=install_daily_panel(conn,width)
        assert result['occurrences']==3903
        assert conn.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        return result
    finally:
        conn.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width',type=int,action='append')
    args=parser.parse_args()
    widths=args.width or s.available_widths()
    with ThreadPoolExecutor(max_workers=min(8,len(widths))) as pool:
        results=list(pool.map(update_width,widths))
    out=s.DATA/'validacion_panel_fecha.json'
    out.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False,indent=2))
