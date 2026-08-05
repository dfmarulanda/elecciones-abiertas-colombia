# Public documentation / Documentación pública

This folder is the reader-facing record for Elecciones Abiertas Colombia. It describes the checked-in contracts, source catalog, fixture release, and operating rules; it is not an electoral result publication.

Esta carpeta es el registro público para lectores de Elecciones Abiertas Colombia. Describe los contratos, catálogo de fuentes, release de prueba y reglas operativas incluidos en el repositorio; no es una publicación de resultados electorales.

## Current status / Estado actual

- **ES:** La selección pública activa es `fixture-2026-round2-v1`, un release sintético de desarrollo; no representa resultados reales ni es publicable como dato electoral. El E-26 nacional de segunda vuelta del CNE está verificado como fuente candidata. Hay un candidato local, nacional y no sintético, pero no está publicado ni activado.
- **EN:** The active public selection is `fixture-2026-round2-v1`, a synthetic development release; it does not represent real results and is not publishable as election data. The CNE’s national second-round E-26 is verified as a candidate source. A local, national-only, non-synthetic candidate exists, but is neither published nor active.

The national pre-count record completed with immutable raw-byte storage before parsing. A non-active geographic sample covers 1/14,438 places and 36/122,020 mesas; its 36 mesa records exactly match the sampled-place aggregate, but that sample check is not aggregate-release reconciliation. The resumable full-scope mesa crawl is running at 2 requests per second per host, with protocol retries and no keepalive connections. Full scope means every planned identifier is attempted; it does not mean every mesa is retrieved or that coverage is 100%, and the crawl is not complete. Department, municipality, and zone aggregate collection is implemented but is not run concurrently with the mesa crawl. Independent human double entry of CNE E-26, full coverage, reconciliation, statistical/FDR validation, and product gates remain blockers. No page here asserts a production deployment or a published real-data release.

El registro nacional de preconteo terminó con almacenamiento inmutable de bytes crudos antes del parseo. Una muestra geográfica no activa cubre 1/14.438 puestos y 36/122.020 mesas; sus 36 mesas coinciden exactamente con el agregado de ese puesto, pero esa comprobación de muestra no es conciliación agregada de release. El crawl de mesas de alcance completo, reiniciable, está en ejecución a 2 solicitudes por segundo por host, con reintentos de protocolo y sin conexiones persistentes. Alcance completo significa intentar cada identificador planificado; no significa recuperar todas las mesas ni tener 100% de cobertura, y el crawl no está completo. La recolección agregada de departamento, municipio y zona está implementada, pero no se ejecuta en paralelo con el crawl de mesas. Siguen bloqueando la doble digitación humana independiente del E-26, la cobertura completa, conciliación, validación estadística/FDR y gates de producto. Ninguna página afirma un despliegue productivo ni un release real publicado.

## Documents / Documentos

| Topic / Tema                                                                      | Document / Documento                                                               |
| --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Method, limits, and review priorities / Método, límites y prioridades de revisión | [Methodology / Metodología](methodology.md)                                        |
| Checked-in official sources / Fuentes oficiales incluidas                         | [Source catalog / Catálogo de fuentes](sources.md)                                 |
| Terms and states / Términos y estados                                             | [Glossary / Glosario](glossary.md)                                                 |
| Inclusive access and privacy / Acceso inclusivo y privacidad                      | [Accessibility and privacy / Accesibilidad y privacidad](accessibility-privacy.md) |
| Read-only API / API de solo lectura                                               | [API guide / Guía de API](api.md)                                                  |
| Immutable releases and operations / Releases inmutables y operaciones             | [Release operations / Operaciones de releases](release-operations.md)              |
| Reporting and recording corrections / Reporte y registro de correcciones          | [Corrections / Correcciones](corrections.md)                                       |
| Deployment handoff / Entrega de despliegue                                        | [Deployment runbook / Runbook de despliegue](deployment.md)                        |
| First candidate-release note / Nota del primer release candidato                  | [Release notes / Notas de release](release-notes.md)                               |

Primary technical boundaries are the frozen [OpenAPI contract](../../packages/contracts/openapi.json), [source catalog](../../config/sources/presidencia-2026-segunda-vuelta.json), [active-release pointer](../../data/manifests/current-release.json), and [active fixture manifest](../../data/manifests/fixture-2026-round2-v1.json).
