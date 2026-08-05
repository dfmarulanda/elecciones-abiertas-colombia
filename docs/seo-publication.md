# Publicación e indexación

Las páginas de resultados sólo se indexan cuando el release activo es **publicado**, no sintético, tiene cobertura completa (`expected = retrieved = parsed`, sin faltantes, ambigüedades o exclusiones) y la conciliación pasó sin excepciones. Un release candidato, retirado, parcial, no disponible o de fixture se entrega con `noindex, nofollow`.

`NEXT_PUBLIC_SITE_URL` debe ser el origen canónico de producción. Sin ese valor no se emite un catálogo de sitemaps: los previews de Vercel no deben convertirse en URLs canónicas.

La ruta `/sitemap.xml` es un índice. Sus particiones se regeneran como máximo cada hora y sólo incluyen portada, resultados, departamentos y municipios con hechos publicados. Cada URL aparece en español e inglés; por ello una partición contiene como máximo 25.000 unidades (50.000 URLs). No se generan mesas, puestos ni zonas masivamente: esas rutas se mantienen `noindex` salvo que una página individual tenga resultado y procedencia únicos en un release completo.

Las rutas territoriales del sitemap incluyen `release` y `election` para fijar la lectura a la publicación inmutable activa. No se usa el primer release que devuelva el API como un valor implícito.

Las páginas E-14 se mantienen `noindex` y canonicalizan a la mesa: son sólo un índice de enlaces salientes oficiales y no contienen PDFs, copias, OCR ni transcripciones.
