import importlib.util
import math
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / 'vendor_python'))


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('preparar'), 'Falta preparación de grilla')
        import preparar
        self.g = preparar

    def test_hexagon_width_area_and_neighbors(self):
        poly = self.g.hexagon(0, 0)
        self.assertAlmostEqual(poly.bounds[2] - poly.bounds[0], 50, places=7)
        self.assertAlmostEqual(poly.area, 2500 * math.sqrt(3) / 2, places=7)
        for q, r in [(1, 0), (0, 1), (-1, 1)]:
            neighbor = self.g.hexagon(q, r)
            self.assertLess(poly.intersection(neighbor).area, 1e-7)
            self.assertAlmostEqual(poly.distance(neighbor), 0, places=7)

    def test_assignment_of_centers_edges_and_vertices(self):
        for q, r in [(0, 0), (5, -8), (7800, 170000)]:
            x, y = self.g.center(q, r)
            self.assertEqual(self.g.axial(x, y), (q, r))
        self.assertEqual(self.g.axial(25, 0), (0, 0))
        self.assertEqual(self.g.axial(25 - 1e-6, 0), (0, 0))
        self.assertEqual(self.g.axial(25 + 1e-6, 0), (1, 0))
        for x, y in self.g.hexagon(0, 0).exterior.coords:
            q, r = self.g.axial(x, y)
            self.assertLess(self.g.hexagon(q, r).distance(self.g.Point(x, y)), 1e-7)

    def test_quality_categories(self):
        self.assertEqual(self.g.quality('Exacta (punto publicado o indicado)'), 'exacta')
        self.assertEqual(self.g.quality('Aproximada — calle, dirección o recorrido'), 'calle')
        self.assertEqual(self.g.quality('Aproximada — centroide de área'), 'centroide')
        self.assertEqual(self.g.quality('Aproximada — heredada sin método documentado'), 'heredada')
        with self.assertRaises(ValueError):
            self.g.quality('desconocida')

    def test_source_counts_and_occurrence_identifiers(self):
        rows = self.g.read_points()
        self.assertEqual(len(rows), 4109)
        self.assertEqual(len({r['id'] for r in rows}), 4109)
        self.assertEqual(sum(r['quality'] == 'exacta' for r in rows), 1078)
        self.assertEqual({r['year'] for r in rows}, {2018, 2019, 2020, 2023, 2024, 2025, 2026})


if __name__ == '__main__':
    unittest.main()
