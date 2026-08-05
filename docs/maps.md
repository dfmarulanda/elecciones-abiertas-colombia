# Límites y mapas

El visor territorial usa únicamente límites departamentales; no representa puestos de votación, zonas ni mesas como puntos. Una coordenada de municipio nunca se usa como sustituto de una coordenada de mesa.

## Referencia fijada

- Productor y atribución: `© DANE — Marco Geoestadístico Nacional, Territoriales DANE 2025`.
- Capa: `Territoriales_DANE/Serv_Territoriales_DANE_2025/MapServer/1`, capa 1, Departamentos.
- Consulta oficial: <https://geoportal.dane.gov.co/mparcgis/rest/services/Territoriales_DANE/Serv_Territoriales_DANE_2025/MapServer/1/query?where=1%3D1&outFields=dpto_ccdgo%2Cdpto_cnmbr&returnGeometry=true&f=geojson&outSR=4326&maxAllowableOffset=0.01>.
- Recuperada: `2026-08-04T03:51:30Z`; respuesta oficial SHA-256: `7e0566ecaacaa99b616b1f3031cd474270fd0e5211a05a331f4c7bfd7fcca3c3`.
- Derivado local revisado: `apps/web/public/maps/dane-departments-2025-simplified.geojson`; SHA-256: `a31064525fea7ad70e6cac9cc0a3a5c1d034f4f6b61cd822b9314b09a821083f`; transformación: `dane-arcgis-max-allowable-offset-0.01/1.0.0+local-final-lf/1.0.0`.
- Simplificación: `maxAllowableOffset=0.01` es aplicada por el servicio DANE en la consulta GeoJSON. Conserva un límite departamental legible para el visor; no es una fuente para medir superficies o distancias. La fijación local sólo normaliza un salto de línea final para empaquetado reproducible.

El archivo se empaqueta localmente y se carga sólo al abrir el mapa. La experiencia pública no depende de CORS, disponibilidad ni cambios del geoservicio de DANE en tiempo de consulta. MapLibre carga la capa GeoJSON y verifica sus elementos visibles; una superficie SVG de presentación, alimentada por el mismo GeoJSON filtrado, preserva los polígonos cuando una composición WebGL no es capturable. No es una segunda fuente ni una geometría inferida.

## Identidades y cobertura

`apps/web/lib/department-map.ts` contiene una tabla de equivalencia revisada, unidireccional y explícita. Incluye sólo los IDs de departamentos conocidos de la fijación, los snapshots de preconteo disponibles y los IDs `r1:dep:*` y `r2:dep:*` del paquete MMV 2022. El código y el nombre de una fuente **no** se comparan de forma difusa en el navegador. Los consulados 2022 y cualquier ID no revisado se omiten del mapa.

La omisión es deliberada: la ausencia de una equivalencia no se transforma en cero, ni se dibuja fuera del territorio, ni se infiere una ubicación. Los valores siguen disponibles en la tabla de resultados.

## Lectura y accesibilidad

El color teal es una señal de presencia territorial y nunca identifica candidaturas, partidos o una conclusión de integridad. El mapa es una visualización de presentación sin foco ni control de teclado; la tabla equivalente es la interacción accesible y conserva nombre de departamento, valor en texto, foco visible y enlaces. La hoja se abre a pantalla completa en móvil. El detalle de procedencia del límite queda detrás de una divulgación para que la lectura inicial se concentre en el resultado.

El mapa sólo selecciona una fila; no altera filtros ni crea datos nuevos. Los enlaces en la tabla conservan los filtros URL-addressable ya activos.
