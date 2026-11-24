import sqlite3
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import servidor as s


class DailyPanelTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
          CREATE TABLE hexagons(id TEXT,q INT,r INT,x REAL,y REAL,district TEXT,subprefecture TEXT,boundary INT,municipal_area REAL);
          CREATE TABLE points(id TEXT,year INT,name TEXT,date TEXT,lat REAL,lon REAL,x REAL,y REAL,q INT,r INT,hex_id TEXT,quality TEXT,district TEXT,subprefecture TEXT);
          INSERT INTO hexagons VALUES
          ('H50_0_0',0,0,0,0,'A','Uno',0,2165),
          ('H50_1_0',1,0,50,0,'B','Dos',0,2165),
          ('H50_2_0',2,0,100,0,'A','Uno',0,2165);
          INSERT INTO points VALUES
          ('p1',2019,'Bloco A','2019-02-01',-23,-46,0,0,0,0,'H50_0_0','exacta','A','Uno'),
          ('p2',2019,'Bloco A','2019-02-01',-23,-46,0,0,0,0,'H50_0_0','exacta','A','Uno'),
          ('p3',2019,'Bloco B','2019-02-01',-23,-46,50,0,1,0,'H50_1_0','calle','B','Dos'),
          ('p4',2019,'Bloco C','2019-02-02',-23,-46,50,0,1,0,'H50_1_0','centroide','B','Dos');
        ''')

    def tearDown(self):
        self.db.close()

    def test_daily_keys_zero_dates_and_different_occurrence_vs_block_counts(self):
        rows=list(s.daily_panel_rows(self.db,{'year':'2019','quality':'analisis','district':'A','width':'50'}))
        self.assertEqual(len(rows),4)
        self.assertEqual(len({(r['hex_id'],r['fecha']) for r in rows}),4)
        a=next(r for r in rows if r['hex_id']=='H50_0_0' and r['fecha']=='2019-02-01')
        self.assertEqual(a['n_ocurrencias'],2)
        self.assertEqual(a['n_blocos'],1)
        self.assertEqual(a['blocos'],'["Bloco A"]')
        self.assertEqual(a['ocurrencia_ids'],'["p1","p2"]')
        self.assertEqual(a['n_ocurrencias_adyacentes'],1)
        self.assertEqual(a['n_blocos_adyacentes'],1)
        self.assertEqual(a['n_hexagonos_adyacentes'],1)
        self.assertTrue(all(r['n_ocurrencias']==0 for r in rows if r['fecha']=='2019-02-02'))
        self.assertNotIn('tratado',a)

    def test_date_selection_exports_only_that_date(self):
        rows=list(s.daily_panel_rows(self.db,{'year':'2019','date':'2019-02-02','quality':'todas','width':'50'}))
        self.assertEqual(len(rows),3)
        self.assertEqual({r['fecha'] for r in rows},{'2019-02-02'})
        self.assertEqual(sum(r['n_ocurrencias'] for r in rows),1)

    def test_neighbors_have_six_directions_in_each_width(self):
        for width in [25,50,100,150,200,300,500]:
            ids=s.neighbor_ids(f'H{width}_5_7')
            self.assertEqual(len(set(ids)),6)
            self.assertNotIn(f'H{width}_5_7',ids)
            self.assertIn(f'H{width}_6_7',ids)

    def test_invalid_calendar_date_is_rejected(self):
        with self.assertRaises(ValueError):
            s.point_filter({'year':'2019','date':'2019-02-31'})

    def test_direct_and_neighbor_flags_can_both_be_one(self):
        rows=list(s.daily_panel_rows(self.db,{'date':'2019-02-01','width':'50'}))
        a=next(r for r in rows if r['hex_id']=='H50_0_0')
        self.assertEqual((a['hay_bloco'],a['adyacente_a_bloco']),(1,1))
        self.assertEqual(a['n_ocurrencias'],2)
        self.assertEqual(a['n_ocurrencias_adyacentes'],1)

    def test_active_coverage_is_explicit_and_retains_only_nonzero_context(self):
        rows=list(s.daily_panel_rows(self.db,{'year':'2019','coverage':'active','width':'50'}))
        self.assertEqual({r['fecha'] for r in rows},{'2019-02-01'})
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r['hay_bloco'] or r['adyacente_a_bloco'] for r in rows))

    def test_materialized_daily_counts_and_complete_sql_panel(self):
        self.assertIsNotNone(importlib.util.find_spec('actualizar_paneles'),'Falta base diaria persistente')
        from actualizar_paneles import install_daily_panel
        install_daily_panel(self.db,50)
        self.assertEqual(self.db.execute('SELECT count(*) FROM panel_fecha').fetchone()[0],6)
        a=dict(self.db.execute("SELECT * FROM panel_fecha WHERE hex_id='H50_0_0' AND fecha='2019-02-01'").fetchone())
        self.assertEqual((a['n_blocos'],a['n_ocurrencias'],a['hay_bloco'],a['adyacente_a_bloco']),(1,2,1,1))
        self.assertEqual((a['n_blocos_adyacentes'],a['n_ocurrencias_adyacentes']),(1,1))


if __name__=='__main__':
    unittest.main()
