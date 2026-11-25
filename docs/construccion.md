# Cómo se construyó la base

La unidad de observación es una aparición de un bloco en la programación de una edición. El mismo nombre puede aparecer varias veces, incluso el mismo día. La versión 1.0.0 reúne 4.109 registros de 2018, 2019, 2020, 2023, 2024, 2025 y 2026. La serie carece de observaciones para 2021 y 2022.

## De la programación a la tabla

Las agendas de G1 aportaron los registros de 2018 y 2019. Para las demás ediciones se consultaron, según el año, portarias, anexos, programas municipales y otras referencias documentadas. Se reunieron los nombres, fechas, horarios y calles publicados y se incorporaron rectificaciones identificadas en fuentes posteriores. Por ejemplo, la revisión de 2024 añadió seis inclusiones posteriores al programa. Cada fila conserva el identificador disponible en el documento, las referencias empleadas y las limitaciones conocidas. Los balances municipales agregados no permiten confirmar la realización de cada desfile. [Procedimiento y rectificaciones por edición](../LEEME_fuentes_y_formato.txt)

## De la dirección al punto

Cuando había un punto publicado o indicado como tal, se conservó con su procedencia. Para otras ubicaciones se usaron direcciones, tramos de calle, intersecciones, referencias históricas o centroides territoriales. La clasificación distingue 1.078 puntos exactos según la fuente, 2.835 aproximados por calle o recorrido, 179 centroides y 17 coordenadas heredadas sin método documentado. Para juzgar un punto concreto hay que leer juntos el método, el proveedor, la dirección y las observaciones.

**Uso de inteligencia artificial y revisión humana.** Según la declaración del responsable del proyecto, se utilizó IA para proponer coordenadas, ayudar a normalizar campos y crear la aplicación. El responsable revisó la base consolidada para comprobar su corrección. La documentación de v1.0.0 describe esa revisión a escala de la base. Para cada registro, la evidencia disponible es la consignada en sus campos de fuente, método y verificación.

## Del punto al hexágono

La aplicación usa la latitud y la longitud consolidadas. Las proyecta a SIRGAS 2000 / UTM zona 23S (EPSG:31983) y asigna cada punto a la grilla regular. En la grilla incluida, los lados opuestos de cada hexágono están separados por 50 m. Para cada fecha y filtro de precisión se cuentan las celdas municipales con al menos un punto. Las seis celdas que comparten un lado con una celda ocupada permiten estudiar la proximidad. Los recorridos dibujados para 2026 son una capa documental aparte. [Ejemplo reproducible del mapa](diccionario.md#ejemplo-del-mapa)

## Qué queda abierto en esta versión

En v1.0.1 queda un punto fuera del municipio. [Cotejo de fuentes y coordenadas](revision-v1.0.1.md) El cotejo de 2025 se publicó en la [revisión v1.0.2](revision-v1.0.2.md). La bitácora documenta también discrepancias territoriales y recorridos sin emparejamiento único. Antes de interpretar una celda como expuesta, conviene comprobar el origen del punto y cuánto cambia el resultado con el filtro de precisión. [Revisión de materiales](revision_material.md) · [Fuentes y permisos](permisos-datos.md)
