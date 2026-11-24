import importlib.util
import sqlite3
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('servidor'), 'Falta servidor y exportación')
        import servidor
        self.s = servidor
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE hexagons(id TEXT,q INT,r INT,x REAL,y REAL,district TEXT,subprefecture TEXT,boundary INT,municipal_area REAL);
        CREATE TABLE points(id TEXT,year INT,name TEXT,date TEXT,lat REAL,lon REAL,x REAL,y REAL,q INT,r INT,hex_id TEXT,quality TEXT,district TEXT,subprefecture TEXT);
        INSERT INTO hexagons VALUES ('a',0,0,0,0,'Sé','Sé',0,2165),('b',1,0,50,0,'Sé','Sé',0,2165),('c',2,0,100,0,'Moema','Vila Mariana',0,2165);
        INSERT INTO points VALUES ('1',2019,'Bloco A','2019-01-01',-23,-46,0,0,0,0,'a','exacta','Sé','Sé'),('2',2019,'Bloco B','2019-01-01',-23,-46,0,0,0,0,'a','centroide','Sé','Sé'),('3',2020,'Bloco C','2020-01-01',-23,-46,100,0,2,0,'c','calle','Moema','Vila Mariana');
        ''')

    def tearDown(self):
        if hasattr(self, 'db'):
            self.db.close()

    def test_filters_compose_year_territory_precision_and_search(self):
        rows = self.s.selected_points(self.db, {'year':'2019','district':'Sé','quality':'analisis','search':'Bloco'})
        self.assertEqual([r['id'] for r in rows], ['1'])
        self.assertEqual(self.s.selected_points(self.db, {'year':'2019','district':'Moema'}), [])

    def test_panel_contains_zero_cells_and_keeps_years(self):
        rows = list(self.s.panel_rows(self.db, {'district':'Sé','quality':'analisis'}, years=[2019,2020]))
        self.assertEqual(len(rows), 4)
        self.assertEqual(sum(r['n_ocurrencias'] for r in rows), 1)
        self.assertEqual(sum(r['tratado'] for r in rows), 1)
        self.assertEqual({r['anio'] for r in rows}, {2019,2020})

    def test_low_quality_is_included_only_explicitly(self):
        self.assertEqual(len(self.s.selected_points(self.db, {'year':'2019'})), 1)
        self.assertEqual(len(self.s.selected_points(self.db, {'year':'2019','quality':'todas'})), 2)

    def test_time_bands_filter_all_panel_queries_by_parade_hour(self):
        times = {'1': {'parade_time':'05:30'}, '2': {'parade_time':'14:00'},
                 '3': {'parade_time':''}}
        with patch.object(self.s, 'source_details', return_value=times):
            self.assertEqual([r['id'] for r in self.s.selected_points(self.db, {'time':'madrugada','quality':'todas'})], ['1'])
            self.assertEqual([r['id'] for r in self.s.selected_points(self.db, {'time':'tarde','quality':'todas'})], ['2'])
            self.assertEqual([r['id'] for r in self.s.selected_points(self.db, {'time':'sin-hora','quality':'todas'})], ['3'])
            self.assertEqual(self.s.selected_points(self.db, {'time':'noche','quality':'todas'}), [])

    def test_reject_unknown_time_band(self):
        with self.assertRaisesRegex(ValueError, 'horario'):
            self.s.selected_points(self.db, {'time':'inventada'})

    def test_reject_unknown_quality_and_year(self):
        with self.assertRaises(ValueError):
            self.s.selected_points(self.db, {'year':'2021'})
        with self.assertRaises(ValueError):
            self.s.selected_points(self.db, {'quality':'inventada'})


if __name__ == '__main__':
    unittest.main()
