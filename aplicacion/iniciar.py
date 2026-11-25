"""Abre una instancia existente o inicia el mapa en el navegador."""
import gzip
import shutil
import tempfile
import subprocess
import sys
import urllib.request
import webbrowser
from pathlib import Path

def preparar_base():
    datos = Path(__file__).resolve().parent / 'datos'
    destino = datos / 'v1.0.4' / 'mapa.sqlite'
    destino.parent.mkdir(exist_ok=True)
    if destino.exists():
        return
    with tempfile.NamedTemporaryFile(dir=destino.parent, delete=False) as tmp:
        temporal = Path(tmp.name)
    try:
        with gzip.open(datos / 'mapa.sqlite.gz', 'rb') as origen, temporal.open('wb') as salida:
            shutil.copyfileobj(origen, salida)
        temporal.replace(destino)
    finally:
        temporal.unlink(missing_ok=True)


preparar_base()
URL = 'http://127.0.0.1:8765'
try:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(URL + '/api/meta', timeout=2) as response:
        if response.status != 200:
            raise OSError('Servidor no disponible')
    webbrowser.open(URL)
    print('Se abrió el mapa que ya está en ejecución.')
except OSError:
    subprocess.run([sys.executable,str(Path(__file__).with_name('servidor.py')),'--open'],check=True)
