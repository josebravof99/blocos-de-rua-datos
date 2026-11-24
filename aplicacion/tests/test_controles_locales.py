"""Comprobaciones de los controles HTTP sin iniciar una generación de grilla."""
import io
import json
import sys
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import servidor as atlas


class ControlesLocales(unittest.TestCase):
    def setUp(self):
        self.handler = object.__new__(atlas.Handler)
        self.handler.server = SimpleNamespace(server_port=8765)
        self.handler.headers = Message()
        self.handler.headers['Host'] = '127.0.0.1:8765'
        self.handler.path = '/api/builds'
        self.handler.send_error = Mock()
        self.handler.json_response = Mock()

    def test_origen_de_la_app(self):
        self.handler.headers['Origin'] = 'http://127.0.0.1:8765'
        with patch.object(atlas.SimpleHTTPRequestHandler, 'parse_request', return_value=True):
            self.assertTrue(self.handler.parse_request())

    def test_descarta_origen_ajeno(self):
        self.handler.headers['Origin'] = 'https://example.org'
        with patch.object(atlas.SimpleHTTPRequestHandler, 'parse_request', return_value=True):
            self.assertFalse(self.handler.parse_request())
        self.assertEqual(self.handler.send_error.call_args.args[0], 403)

    def test_largo_se_valida_antes_de_leer(self):
        self.handler.headers['Content-Type'] = 'application/json'
        self.handler.headers['Content-Length'] = '1025'
        self.handler.rfile = Mock()
        self.handler.do_POST()
        self.handler.rfile.read.assert_not_called()
        self.assertEqual(self.handler.json_response.call_args.args[1], 413)

    def test_solicitud_normal_de_grilla(self):
        body = json.dumps({'width': 350}).encode()
        self.handler.headers['Content-Type'] = 'application/json'
        self.handler.headers['Content-Length'] = str(len(body))
        self.handler.rfile = io.BytesIO(body)
        with patch.object(atlas, 'available_widths', return_value=[50]), patch.object(atlas, 'run_custom_build') as build:
            self.handler.do_POST()
            build.assert_called_once_with(350)

    def test_exportacion_conserva_numeros_y_protege_texto(self):
        self.assertEqual(atlas.safe_csv_value(-23.5), -23.5)
        self.assertEqual(atlas.safe_csv_value('  =1'), "'  =1")
        self.assertEqual(atlas.safe_csv_value('Sé'), 'Sé')
