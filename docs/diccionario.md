# Diccionario del consolidado

El CSV usa UTF-8, separador de coma y punto decimal. Excel reúne los mismos campos en la hoja **Consolidado**. Los vacíos y las expresiones como «No informado en el JSON» conservan ausencias de información. Un horario vacío, por ejemplo, indica que la fila carece de ese dato.

| Columna, en orden de archivo | Contenido e interpretación |
| --- | --- |
| Año | Edición de la programación, expresada con cuatro dígitos. |
| ID en fuente | Identificador que permite localizar la entrada en su fuente. Puede ser un número, texto o una posición de fila asignada como referencia. Su alcance depende del documento. |
| Nombre del bloco | Nombre registrado para esa aparición. Un nombre puede repetirse en varias filas. |
| Fecha | Día programado del desfile, en formato AAAA-MM-DD. |
| Hora de concentración | Hora anunciada para la reunión previa. |
| Hora de desfile | Hora anunciada de salida o inicio del desfile. |
| Hora de dispersión | Hora anunciada para el cierre o dispersión. |
| Precio | Información de acceso o precio y, cuando consta, la regla de gratuidad o la falta de información. Campo de texto. |
| Dirección de concentración | Dirección o punto de encuentro descrito en el registro. |
| Recorrido / calles | Itinerario textual o tramo informado. La geometría dibujada en el mapa tiene cobertura propia. |
| Dirección de dispersión | Lugar indicado para el término o dispersión. |
| Latitud | Latitud del punto utilizado en el mapa, en grados decimales. Leer junto con la clase de georreferenciación. |
| Longitud | Longitud del mismo punto, en grados decimales. En GeoJSON el orden del par es longitud, latitud. |
| Región / zona | Referencia territorial textual del programa. Puede diferir de la ubicación que resulta de cruzar el punto con el mapa. |
| Barrio | Barrio consignado por la fuente, cuando está disponible. |
| Tipo de fuente | Clase del material que respalda la entrada, por ejemplo una agenda o una publicación oficial. |
| Estado de verificación | Qué respalda la evidencia sobre programación, autorización o realización. Consultar antes de contar eventos como realizados. |
| ID de fuente | Uno o más códigos del catálogo de fuentes. Pueden recoger por separado la programación y la geocodificación. |
| Referencia directa | Enlace o enlaces de respaldo. Si remiten a un geocodificador, el ID de fuente y la hoja **Fuentes** ayudan a localizar el documento del desfile. |
| Observaciones / límites | Notas específicas sobre correcciones, ausencias, decisiones y dudas de interpretación. |
| Tipo de coordenada | Etiqueta general asignada al punto. El desglose más detallado figura en **Clase de georreferenciación**. |
| Método / precisión | Descripción del procedimiento o evidencia de ubicación. La precisión declarada es cualitativa. |
| Latitud exacta | Latitud del punto clasificado como exacto según su fuente, cuando corresponde. |
| Longitud exacta | Longitud que forma el par con **Latitud exacta**. |
| Latitud aproximada | Latitud consignada en el par aproximado, cuando corresponde. |
| Longitud aproximada | Longitud que forma el par con **Latitud aproximada**. |
| Clase de georreferenciación | Categoría detallada que alimenta los filtros de la aplicación: exacta, aproximada por calle o recorrido, centroide o heredada. |
| Proveedor / fuente de coordenadas | Publicación, servicio o referencia de donde procede la ubicación. Puede diferir de la fuente del calendario. |

## Ejemplo del mapa

Abre la aplicación de v1.0.12 y elige **2026 → sábado 7 de febrero → 50 m**. Usa toda la ciudad, todos los distritos y horarios, y deja la búsqueda vacía. Cambia solo **Precisión de las coordenadas**. Estos son los resultados del resumen municipal para la grilla incluida.

| Precisión seleccionada | Ocurrencias incluidas | Hexágonos con al menos un punto |
| --- | ---: | ---: |
| Solo exactas según fuente | 105 | 97 |
| Exactas + aproximadas por calle | 115 | 106 |

Al incluir los diez puntos aproximados aparecen nueve celdas ocupadas adicionales. Varias ocurrencias pueden compartir una celda. La diferencia mide la sensibilidad del mapa a la selección de coordenadas. La captura de la portada usa una grilla de 300 m; al cambiar el ancho también cambia el conteo de celdas.

**Una fila que explica por qué importa la precisión.** En el CSV, filtra el 7 de febrero de 2026 y busca **BLOCO LOVE LIFE**. La entrada refiere a la fila 379 del anexo del programa y cita los códigos `SRC-2026-PROGRAMA` y `SRC-OSM-PHOTON`. El programa indica Santo Amaro y un tramo de R. Laguna. La coincidencia del geocodificador sitúa el punto en Mooca. En «Exactas + aproximadas por calle», la exportación del mapa lo identifica como `2026-0012`, en la celda `H50_-78653_170762`. En «Solo exactas según fuente» queda excluido. La discrepancia queda abierta en esta versión: para un estudio por distrito, merece un cotejo específico antes de atribuir ese desfile a Mooca.

[Construcción de la base](construccion.md) · [Abrir el consolidado CSV](../datos/blocos.csv)
