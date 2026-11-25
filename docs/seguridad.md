# Revisión de seguridad de la aplicación local

**24 de noviembre de 2026.** La revisión cubrió el servidor HTTP de la edición para escritorio, la generación de grillas, las consultas SQLite, el contenido que muestra el mapa, las exportaciones y los avisos publicados para las dependencias instaladas.

| Componente | Hallazgo y corrección |
| --- | --- |
| Servidor local | El servidor escuchaba en la interfaz local, pero aceptaba solicitudes destinadas a otros nombres de host. Ahora valida el host y el puerto, comprueba el origen cuando el navegador lo envía y rechaza solicitudes que el navegador identifica como procedentes de otro sitio u origen hermano. |
| Generación de grillas | La operación aceptaba cuerpos de solicitud sin un límite explícito y tipos de contenido distintos de JSON. Ahora exige JSON, un tamaño declarado de hasta 1 KiB y un ancho entero. Conserva el límite de una generación simultánea. Las conexiones tienen un tiempo máximo de espera por operación de socket. |
| Descargas | Los filtros de fecha y año se normalizan antes de incorporarlos al nombre del archivo. La protección de las celdas de texto del CSV también reconoce indicadores de fórmula precedidos por espacios. Las coordenadas numéricas conservan su tipo. Se admiten dos exportaciones simultáneas para limitar la carga sobre el equipo. |
| Interfaz | La línea de tiempo escapa las etiquetas obtenidas de los datos. La política de contenido permite scripts locales, restringe la carga de imágenes a los orígenes necesarios para el mapa e impide que otra página enmarque la aplicación. |

## Comprobaciones

Las 26 pruebas automatizadas pasaron con la base de 50 m disponible. Cubren, entre otras funciones, las relaciones espaciales, los filtros y el panel diario. Cinco pruebas añadidas en esta revisión cubren el origen HTTP, el tamaño de las solicitudes, la validación de un pedido normal de grilla y la protección de texto exportado. En Edge se abrió la aplicación con la política de contenido activa, se cambió la selección a 2019 y se descargó un CSV con sus 545 registros.

La consulta por versión en OSV para NumPy 2.5.5, Shapely 2.2.0, pyproj 3.8.0, certifi 2026.11.20 y Leaflet 1.9.4 devolvió cero avisos asociados en la fecha de revisión. La instalación de Python también pasó la comprobación de compatibilidad de dependencias de pip. El resultado corresponde a esas versiones; el archivo de requisitos admite otras. [Base de avisos OSV](https://osv.dev/)

## Alcance de uso

La aplicación está preparada para ejecutarse en el equipo de quien lo utiliza, con el servidor en la interfaz de bucle local. El fondo de calles se obtiene de OpenStreetMap. Una descarga municipal completa puede ocupar bastante espacio incluso con una sola exportación. Esta revisión cubre la configuración local publicada. Un despliegue multiusuario o accesible desde Internet requeriría evaluar autenticación, cuotas de recursos y la configuración del servidor. Quedan fuera de esta revisión el sistema operativo del usuario, la auditoría interna de bibliotecas de terceros y la certificación independiente.
