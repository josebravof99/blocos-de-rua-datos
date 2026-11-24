import csv
import gzip
import io
import json
import sys
import unittest
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP))
import servidor


@unittest.skipUnless(servidor.DB.exists(), 'Preparar la base antes de la integración')
class ActualDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = servidor.connection()

    def tearDown(self):
        self.conn.close()

    def test_all_sources_preserved_and_default_precision(self):
        self.assertEqual(len(servidor.selected_points(self.conn,{'quality':'todas'})),4109)
        self.assertEqual(len(servidor.selected_points(self.conn,{})),3913)
        s = servidor.summary(self.conn,{})
        self.assertEqual(s['cells'],707661)
        self.assertEqual(s['outside'],1)
        self.assertEqual(s['controls']+s['treated'],s['cells'])

    def test_district_panel_and_map_share_same_cohort(self):
        params = {'district':'Moema','subprefecture':'Vila Mariana','quality':'analisis'}
        points = servidor.selected_points(self.conn,params)
        panel = list(servidor.panel_rows(self.conn,params))
        s = servidor.summary(self.conn,params)
        self.assertEqual(len(panel),s['cells']*7)
        self.assertEqual(sum(r['n_ocurrencias'] for r in panel),len(points))
        self.assertTrue(any(r['n_ocurrencias']==0 for r in panel))
        for year in servidor.YEARS:
            year_summary=servidor.summary(self.conn,{**params,'year':str(year)})
            subset=[r for r in panel if r['anio']==year]
            self.assertEqual(sum(r['tratado'] for r in subset),year_summary['treated'])

    def test_visible_grid_does_not_silently_truncate(self):
        p={'year':'2026','bbox':'-46.8,-23.7,-46.4,-23.4','controls':'1'}
        data=servidor.grid_view(self.conn,p)
        self.assertTrue(data['limited'])
        self.assertEqual(data['features'],[])
        p['controls']='0'
        data=servidor.grid_view(self.conn,p)
        self.assertFalse(data['limited'])
        self.assertTrue(data['features'])

    def test_route_ids_reconcile_to_source_rows(self):
        data=json.loads((APP/'auditoria'/'rutas_2026.geojson').read_text(encoding='utf-8'))
        points={p['id']:p for p in servidor.selected_points(self.conn,{'year':'2026','quality':'todas'})}
        self.assertEqual(len(data['features']),511)
        for f in data['features']:
            self.assertEqual(f['geometry']['type'],'LineString')
            self.assertEqual(len(f['properties']['occurrence_ids']),1)
            p=points[f['properties']['occurrence_ids'][0]]
            self.assertEqual(p['date'],f['properties']['fecha'])
            for lon,lat in f['geometry']['coordinates']:
                self.assertTrue(-47.2<lon<-45.8 and -24.3<lat<-23)


if __name__=='__main__':
    unittest.main()
