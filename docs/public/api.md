# API guide / Guía de API

## ES

La API es de solo lectura y está definida por el [OpenAPI congelado](../../packages/contracts/openapi.json) v1.0.0. La base local del contrato es `http://localhost:8000`; este documento no anuncia un endpoint público desplegado. Toda respuesta de datos incluye o se relaciona con un `data_version` inmutable y procedencia. Los ejemplos usan el fixture sintético actual; no son resultados reales.

| Recurso               | Ruta                                   | Parámetros principales                                                                                                                    |
| --------------------- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Resumen electoral     | `GET /api/v1/elections/{slug}/summary` | `data_version`                                                                                                                            |
| Resultados            | `GET /api/v1/elections/{slug}/results` | `data_version`, `cursor`, `limit` (1–200; 50 por defecto), `source_type`, `geography_id`, `geography_level`, `candidate_id`, `format=json | csv` |
| Geografía             | `GET /api/v1/geographies/{id}`         | `data_version`                                                                                                                            |
| Mesa                  | `GET /api/v1/mesas/{id}`               | `data_version`, `source_type`                                                                                                             |
| Índice E-14 de mesa   | `GET /api/v1/mesas/{id}/evidence`      | `data_version`; solo metadatos y enlaces oficiales externos, nunca archivos ni derivados                                                  |
| Comparaciones de mesa | `GET /api/v1/mesas/{id}/comparisons`   | `data_version`                                                                                                                            |
| Boletines             | `GET /api/v1/bulletins`                | `election_slug`, `data_version`                                                                                                           |
| Resultado de boletín  | `GET /api/v1/bulletins/{id}/results`   | `data_version`                                                                                                                            |
| Señales de revisión   | `GET /api/v1/review-signals`           | `election_slug`, `data_version`, `cursor`, `limit`, `minimum_score`, `tier`, `geography_id`                                               |
| Datasets              | `GET /api/v1/datasets`                 | `election_slug`, `data_version`                                                                                                           |
| Descarga de dataset   | `GET /api/v1/datasets/{id}/download`   | `data_version`                                                                                                                            |
| Contrato              | `GET /api/v1/openapi.json`             | —                                                                                                                                         |

La exploración pública normalizada usa pares de publicación expuestos por `GET /api/v1/release-elections`. Para un par publicado, las rutas con ámbito explícito son `GET /api/v1/releases/{release_id}/elections/{election_slug}/results`, las rutas de geografía y mesa del mismo prefijo, y `GET /api/v1/releases/{release_id}/elections/{election_slug}/outcome-sensitivity`. La última puede ser `404` o estar ausente: la interfaz la muestra como **no disponible**, nunca como una cota cero. Los pares 2022 son contexto descriptivo y solo admiten comparación cuando el endpoint entrega un cruce aprobado; coincidencias de nombre no crean equivalencia geográfica ni de candidatura.

El mismo prefijo publica recursos analíticos inmutables: `/analysis/summary`, `/analysis/anomalies` (paginado y filtrable por `anomaly_type`), `/analysis/anomalies/{id}`, `/analysis/model_diagnostics`, `/analysis/validation` y `/analysis/local_sensitivity`. Cada anomalía separa `is_anomaly`, `audit_priority_score` y `explanation.status`; una explicación no borra la detección. Las cinco clases son `structural_arithmetic`, `identity_coverage`, `cross_source_documentary`, `peer_distribution` y `spatial`. Los recursos incluyen procedencia, cobertura/faltantes y `research_preview` con razones de inelegibilidad. Las vistas de pares y espacio permanecen inelegibles hasta que existan artefactos independientes de simulación/validación. **Una anomalía prioriza revisión y no es una probabilidad ni un hallazgo de fraude.**

### Consultas reproducibles

```bash
# Resumen del fixture actual (la versión se puede fijar de forma explícita).
curl 'http://localhost:8000/api/v1/elections/presidencia-2026-segunda-vuelta/summary?data_version=fixture-2026-round2-v1'

# Página JSON filtrada; conserve next_cursor y todos los filtros para la página siguiente.
curl 'http://localhost:8000/api/v1/elections/presidencia-2026-segunda-vuelta/results?data_version=fixture-2026-round2-v1&source_type=pre_count&geography_level=mesa&limit=50'

# Exportación CSV: no acepta cursor.
curl -L 'http://localhost:8000/api/v1/elections/presidencia-2026-segunda-vuelta/results?data_version=fixture-2026-round2-v1&format=csv&source_type=pre_count' -o results.csv

# Señales ordenadas por prioridad, con filtros de versión y geografía.
curl 'http://localhost:8000/api/v1/review-signals?election_slug=presidencia-2026-segunda-vuelta&data_version=fixture-2026-round2-v1&minimum_score=25&geography_id=CO-DC'
```

Los cursores son opacos y firmados. Están ligados a release y al conjunto completo de filtros; no los edite ni reutilice tras cambiar `data_version`, fuente, geografía, candidatura, límite o filtro de señal. Para JSON, lea `page.next_cursor` y envíelo sin modificar. CSV representa el conjunto filtrado completo y rechaza un cursor.

### Procedencia, caché y errores

Cada `ResultFact`, resumen, evidencia y señal expone procedencia: `data_version`, `source_type`, `legal_status`, `source_url`, `retrieved_at`, `content_hash`, `parser_version`, `transform_version` y, cuando existe, `methodology_version`. Los valores métricos son `{value, status}`: `observed` requiere un número (incluido 0); `unknown`, `unavailable` y `not_applicable` requieren `value: null`. Nunca convierta `null` en cero.

Las respuestas JSON incluyen `ETag`, `Vary: Origin` y caché histórica (`public, max-age=3600, stale-while-revalidate=86400`). El contrato OpenAPI y el listado de datasets usan caché inmutable (`public, max-age=31536000, immutable`). Envíe `If-None-Match` para poder recibir `304`. Una descarga de dataset devuelve `302` hacia el objeto inmutable autorizado; en fixture, el modo de datos locales se limita al fixture sintético. El endpoint de evidencia de mesa es solo índice: entrega referencias oficiales externas y procedencia del índice, nunca PDF, proxy, caché, OCR, transcripción ni derivado.

Los errores usan `application/problem+json` con `type`, `title`, `status`, `detail` e `instance`. Casos previstos: `400` para parámetros o cursor inválidos (incluido cursor con CSV), `404` para recurso o release ausente, `503` para modelo de lectura no disponible y `500` para fallo no esperado. La API también ofrece `/healthz` y `/readyz`, que son sondas operativas y no forman parte del contrato público congelado.

La divulgación de toda señal es permanente: **Este puntaje prioriza registros para revisión documental; no mide ni determina fraude. La ausencia de una señal no demuestra que una mesa estuviera libre de errores.**

## EN

The API is read-only and defined by frozen [OpenAPI](../../packages/contracts/openapi.json) v1.0.0. The contract’s local base is `http://localhost:8000`; this document does not advertise a deployed public endpoint. Every data response includes or relates to an immutable `data_version` and provenance. Examples use the current synthetic fixture, not real results.

The endpoint table above applies in English as well. `data_version` pins an immutable release; omitting it selects the active release (currently the synthetic fixture). Result filters are `source_type`, `geography_id`, `geography_level`, and `candidate_id`; review-signal filters are `minimum_score`, `tier`, and `geography_id`. Limits are 1–200, default 50.

The normalized public explorer uses published pairs from `GET /api/v1/release-elections`. For a published pair, scoped results, geography, and mesa routes share `/api/v1/releases/{release_id}/elections/{election_slug}`, and outcome sensitivity is at `/outcome-sensitivity`. That resource may be `404` or absent; the interface presents it as **not available**, never as a zero bound. The 2022 pairs are descriptive context and become comparable only when the endpoint supplies an approved crosswalk; matching names do not establish geographic or candidate equivalence.

The same prefix publishes immutable analytical resources: `/analysis/summary`, `/analysis/anomalies` (paginated and filterable by `anomaly_type`), `/analysis/anomalies/{id}`, `/analysis/model_diagnostics`, `/analysis/validation`, and `/analysis/local_sensitivity`. Each anomaly keeps `is_anomaly`, `audit_priority_score`, and `explanation.status` separate; an explanation never removes detection. The five classes are `structural_arithmetic`, `identity_coverage`, `cross_source_documentary`, `peer_distribution`, and `spatial`. Resources include provenance, coverage/missingness, and `research_preview` with ineligibility reasons. Peer and spatial views remain ineligible until independent simulation/validation artifacts exist. **An anomaly prioritizes review and is not a probability or finding of fraud.**

Cursors are opaque and signed. They are bound to the release and complete filter set; do not edit or reuse them after changing `data_version`, source, geography, candidate, limit, or signal filter. For JSON, pass `page.next_cursor` unchanged. CSV represents the whole filtered set and rejects a cursor.

Provenance contains `data_version`, `source_type`, `legal_status`, `source_url`, `retrieved_at`, `content_hash`, `parser_version`, `transform_version`, and, when present, `methodology_version`. Metric values are `{value, status}`: `observed` requires a number, including 0; `unknown`, `unavailable`, and `not_applicable` require `value: null`. Never turn `null` into zero.

JSON responses use `ETag`, `Vary: Origin`, and historical caching (`public, max-age=3600, stale-while-revalidate=86400`). The OpenAPI document and dataset list use immutable caching (`public, max-age=31536000, immutable`). Send `If-None-Match` to receive `304`. Dataset download returns `302` to an allowed immutable object; fixture local rendering is limited to the synthetic fixture. The mesa evidence endpoint is an index-only response: it returns official outbound references and source-index provenance, never a PDF, proxy URL, cache, OCR, transcription, or derivative.

Errors use `application/problem+json` with `type`, `title`, `status`, `detail`, and `instance`: `400` invalid parameters/cursor, `404` missing resource/release, `503` unavailable read model, and `500` unexpected failure. `/healthz` and `/readyz` are operational probes, not part of the frozen public contract.

The permanent disclosure for every review signal is: **This score prioritizes records for documentary review; it does not measure or determine fraud. Absence of a signal does not prove that a mesa was error-free.**
