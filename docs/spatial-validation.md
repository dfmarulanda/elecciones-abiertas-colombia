# Validación espacial y simulada

La capa espacial analiza residuos ya producidos por el modelo de pares. No
interpreta coordenadas como evidencia de irregularidad, no estima votos
afectados y una señal es sólo un motivo trazable para revisión humana.

Para cada municipio se fija antes de inferir una matriz de vecinos de hasta
cinco unidades de análisis más cercanas, únicamente dentro del municipio y a
20 km o menos. Cada fila se estandariza a suma uno. Se calcula un estadístico
local tipo Moran sobre residuos centrados. Una unidad necesita al menos tres
vecinos y el municipio al menos 100 mesas geocodificadas y elegibles, repartidas
en al menos 100 unidades de análisis elegibles. Geocodes
pobres, filas transfronterizas, unidades co-localizadas y zonas aisladas o
escasas se declaran inelegibles; nunca reciben una puntuación.

El nulo permuta conjuntamente todas las etiquetas de residuo dentro del mismo
municipio y recalcula toda la familia de estadísticos locales con la misma
matriz fija. La prueba es bilateral y usa `p = (b + 1) / (B + 1)`, por lo que
un valor p nunca es cero. Cada resultado publica `B` y su resolución
`1 / (B + 1)`: inicia con 9.999 permutaciones y sólo se amplía a 99.999 cuando
la familia contiene una cola cruda potencialmente reportable. Las hipótesis
se ajustan por Benjamini--Yekutieli. Una señal además requiere `p <= 0.001`,
`q <= 0.05` y magnitud local absoluta de al menos 0,25. Se distinguen
agrupaciones positivas de contrastes espaciales negativos.

Una coordenada a nivel de puesto se analiza una sola vez como puesto. Las
mesas adicionales del mismo puesto quedan explícitamente como
`nonrepresentative_polling_place_mesa`; una señal de puesto no se replica ni
se presenta como una señal independiente por mesa.

La validación sintética usa denominadores observados y conserva la ausencia de
registro cuando existe. Su diseño de estrés incluye jerarquía
departamento--municipio--puesto, sobredispersión beta-binomial, dependencia
composicional, colas pesadas, inflación de ceros y una mezcla de especificación
incorrecta. Las alternativas incluyen inyecciones cercanas a límites de
política (denominador mínimo, umbral de magnitud y saturación). Cada artefacto
registra hashes de entradas, método, perfil, entorno de ejecución y todas las
semillas.

`ci-deterministic` ejecuta 100 nulos y 100 alternativas para regresión
determinista. `full-release-1000x1000` declara 1.000 nulos y 1.000 alternativas
con el presupuesto espacial adaptativo completo. Ningún perfil puede
autoautorizar producción: `production_eligible` y `release_gate_passed`
permanecen falsos hasta que una ejecución completa independiente sobre los
datos auténticos sea revisada y aceptada por el proceso de release.
