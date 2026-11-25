# Cómo usar Blocos de rua de São Paulo

Esta guía corresponde a la [versión v1.0.10](https://github.com/josebravof99/blocos-de-rua-datos/releases/tag/v1.0.10).

Elige un año y una fecha para consultar la programación de ese día. Si seleccionas un distrito, el mapa encuadra la zona. Pulsa un punto para ver el nombre, los horarios y la fuente del desfile. La vista inicial incluye los puntos exactos según la fuente y las aproximaciones por calle. El filtro de precisión permite consultar también centroides y coordenadas heredadas.

## Leer los hexágonos

La grilla incluida tiene 707.661 celdas de 50 metros entre lados opuestos. Los hexágonos con al menos un registro aparecen en rojo y sus vecinos en azul. La opción **Celdas sin exposición registrada** muestra también las celdas vacías al acercar el mapa. En los límites distritales, cada celda pertenece al distrito con el que comparte más superficie.

La aplicación usa SIRGAS 2000 / UTM 23S (EPSG:31983) para medir distancias. El identificador de una celda se conserva en todas las fechas dentro de una misma escala. Puedes generar anchos enteros entre 101 y 2.000 metros desde el selector. Para obtener otra grilla, por ejemplo la de 25 metros, ejecuta desde la raíz del proyecto y vuelve a abrir el mapa:

```sh
python aplicacion/preparar.py --width 25
```

## Descargar una selección

- **Puntos CSV.** Una fila por registro, con nombre, fecha, horarios, precisión, fuente, recorrido informado e identificador de celda.
- **Grilla GeoJSON.gz.** Polígonos completos del territorio seleccionado con sus conteos. El encuadre de la pantalla solo afecta a la vista.
- **Adyacencias CSV.gz.** Pares de identificadores de hexágonos que comparten un lado.
- **Panel CSV.** Una fila por celda y fecha. `n_ocurrencias` cuenta registros y `n_blocos` cuenta nombres distintos normalizados. `adyacente_a_bloco` indica que una celda vecina tiene al menos un registro ese mismo día, incluso al otro lado de un límite distrital.

El calendario contiene las 87 fechas presentes en las fuentes. A 50 metros, el panel municipal con todos los ceros alcanza 61.566.507 filas. Selecciona una fecha o un distrito para obtener un archivo que puedas abrir en una hoja de cálculo. Para analizar todo el territorio, también puedes consultar la vista SQLite `panel_fecha` del archivo `mapa.sqlite` que la aplicación descomprime en una subcarpeta de `aplicacion/datos/` durante el primer inicio.

La exposición se calcula a partir del punto de cada registro. La capa de recorridos de 2026 sirve para consultar el trazado publicado. Los límites distritales de GeoSampa se aplican a todos los años con la misma geometría. [Revisión de fuentes y cartografía](../docs/revision_material.md)

## Licencia y reutilización

El código de la aplicación se distribuye bajo licencia MIT. Consulta las condiciones de cada fuente antes de reutilizar o redistribuir datos y capas geográficas. [Licencia de la aplicación](LICENSE) · [Fuentes y permisos de los datos](../docs/permisos-datos.md)
