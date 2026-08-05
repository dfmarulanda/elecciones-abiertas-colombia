# Methodology / Metodología

## ES — Propósito y alcance

Este proyecto conserva capas de fuente separadas y prioriza registros para revisión documental. No certifica resultados, no adjudica disputas y no reemplaza a las autoridades electorales. Cada hecho conserva tipo de fuente, condición jurídica, URL oficial, fecha de recuperación, hash y versiones de transformación.

La precedencia no convierte una capa en otra:

| Capa                                | Uso permitido                                                                                                                    |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Declaración final controlante       | Controla únicamente los totales y el ámbito geográfico que publique de forma explícita.                                          |
| Escrutinio publicado                | Tiene validez jurídica dentro de su ámbito y granularidad publicados; un agregado nunca se fuerza a ser un hecho final por mesa. |
| E-14 de delegados o transmisión     | Evidencia documental; una extracción no autoritativa no sustituye el original ni una decisión oficial.                           |
| Preconteo                           | Información preliminar, no jurídicamente vinculante.                                                                             |
| Primera vuelta e historia electoral | Contexto descriptivo solamente; no alimenta señales ni cambia resultados.                                                        |

No se infiere un valor final por mesa a partir de una fuente de mayor agregación. La conciliación es determinista: valida identidades canónicas completas (departamento, municipio, puesto y mesa), aplica identidades aritméticas solamente dentro de la misma fuente, bloquea agregaciones con duplicados y compara únicamente campos con la misma granularidad publicada. La cobertura distingue completo, faltante, duplicado y ambiguo; no inventa ausencias.

El preconteo por mesa disponible en esta fuente no publica un denominador de electores inscritos. Se conserva como `unavailable`: no se infiere participación, no se usa cero como elector observado y no se aplica una cota de electores no observada. En particular, `centota=0` con votantes positivos es un centinela de no disponibilidad. Las estadísticas nunca agregan votos afectados verificados.

### Estado de validación estadística

Las señales de pares, espaciales y de sensibilidad siguen siendo funciones experimentales. La verificación interna separa al menos 100 simulaciones nulas puras de al menos 100 alternativas inyectadas, calcula el FDP por ejecución y vincula confusión y potencia por familia/mesa al código, método, cohorte y datos exactos de cada ejecución. Esta implementación aún no equivale a una auditoría independiente ni habilita datos reales. Solo puede aparecer en la demostración sintética para probar el contrato y la interfaz. Las publicaciones reales continúan cerradas para estadísticas y sensibilidad hasta una revisión independiente posterior. Ningún booleano o afirmación manual puede sustituir los artefactos recalculados.

### Sensibilidad del resultado

El análisis de sensibilidad solo se evalúa con hechos de fuente content-addressed incluidos en un registro de confianza y con registros afectados revisados por dos identidades independientes autorizadas. Cada revisión queda hasheada y vinculada al registro, a los hechos exactos y a sus valores. Los registros no resueltos solo pueden aportar cotas explícitas, positivas y observadas en hechos autenticados; sus identificadores de cobertura deben coincidir exactamente y la identidad canónica evita colisiones o solapamientos por separadores. La cota de cambio de margen usa dos votos por voto afectado. Si falta cualquier condición, el estado es `not_evaluable`, no una estimación. Los estados publicados distinguen robustez dentro de las cotas evaluadas, empate o cambio de liderazgo dentro de la cota verificada, y casos posibles solo al incluir registros no resueltos. Son condicionales a esas cotas: no declaran el resultado, intención ni fraude, y nunca convierten señales estadísticas o historia en votos afectados verificados.

### Prioridad de revisión v1

La base determinista usa el máximo aplicable, no la suma entre filas. Las señales estadísticas se suman después, con tope conjunto de 20; el total se limita a 100.

| Condición verificable                                                          | Puntos |
| ------------------------------------------------------------------------------ | -----: |
| Error aritmético verificado **o** registros canónicos en conflicto             |    100 |
| Diferencia documental de al menos 5 votos **o** al menos 2 puntos porcentuales |     70 |
| Diferencia documental de 1–4 votos **y** menos de 2 puntos porcentuales        |     45 |
| Documento oficial esperado faltante, duplicado o ambiguo                       |     25 |
| Señal de pares que supera todas sus puertas                                    |    +10 |
| Señal espacial que supera todas sus puertas                                    |    +10 |

Las cuatro etiquetas públicas y sus rangos exhaustivos son: `documentary_review_prioritized` para 70–100, `documentary_comparison_recommended` para 45–69, `statistical_or_coverage_issue` para 15–44 y `no_review_signals` para 0–14. Se deben leer junto con los componentes, la cobertura y la versión metodológica. Un componente de 10 puntos puede figurar en el detalle aunque el puntaje total siga por debajo del nivel de revisión. No hay otros tiers públicos.

**Divulgación permanente:** Este puntaje prioriza registros para revisión documental; no mide ni determina fraude. La ausencia de una señal no demuestra que una mesa estuviera libre de errores.

### Puertas estadísticas

El modelo de pares es beta-binomial empírico-bayesiano con exclusión de la propia mesa y se ajusta a los conteos enteros numerador/denominador, no a tasas interpoladas. Examina una sola familia completa de métrica/candidatura por ejecución. Tanto la mesa como cada par requieren el denominador propio de esa métrica de al menos 80; electores inscritos solo son necesarios para participación. El grupo es el primer nivel con al menos 30 pares elegibles: puesto, municipio o departamento, siempre sin la mesa evaluada y sin mezclar capas de fuente, versión, elección/ronda o candidatura. Verifica el conteo y digest esperados antes de calcular todos los valores _p_ y una sola corrección Benjamini–Yekutieli. Una señal requiere simultáneamente: (1) cola predictiva EB bilateral ≤ 0,001; (2) _q_ BY ≤ 0,05; (3) residuo estandarizado absoluto ≥ 3,5; y (4) efecto absoluto de al menos 8 puntos porcentuales para participación o participación de candidatura, o 3 para blanco o nulos/no marcados. Un fallback numérico o una aproximación por demasiados estados se marca descriptivo y nunca recibe puntos públicos. Es un indicador de selección, no prueba de error; nunca estima votos afectados.

La prueba espacial usa el artefacto exacto y hasheado de residuales del modelo, no porcentajes brutos. La familia inmutable incluye versión, elección/ronda, capa de fuente, métrica y candidatura; no acepta contexto histórico. Las coordenadas requieren URL, hash, exactitud y granularidad. Si son de puesto, primero se colapsan al puesto: mesas co-localizadas no son observaciones independientes. Dentro de cada municipio exige al menos 100 unidades elegibles, toma hasta cinco vecinas del mismo municipio a 20 km o menos (mínimo tres, empates por identificador) y aplica una nula condicional de etiquetas aleatorias con semilla estable por unidad y al menos 9.999 permutaciones. Ajusta todos los valores _p_ de la familia espacial con Benjamini–Yekutieli. Un producto local positivo se etiqueta como agrupación positiva y uno negativo como contraste espacial; ambos son descripciones de selección, no estimaciones de votos afectados.

No se usa Benford. El historial contextual no es una señal. Una señal no prueba irregularidad, y la falta de una señal no prueba que no existan errores.

### Revisión de anomalías y comparaciones acotadas

Toda identidad aritmética declarada produce `pass`, `fail` o `not_evaluable`; un campo no publicado nunca se trata silenciosamente como aprobado. Los agregados de un release exigen un universo de identidades esperadas completo, único y exacto para cada capa de fuente. Las anomalías públicas conservan su detección (`is_anomaly`) después de revisar una explicación. El estado de explicación es `explained`, `partially_explained`, `no_explanation_found_in_available_data` o `non_evaluable`; este último se usa cuando faltan los metadatos preregistrados de revisión o los datos de fuente disponibles.

Para un vector declarado completo de categorías de papeleta mutuamente excluyentes, la cota inferior mínima de ediciones es `A_min = max(P, N)`, donde `P` y `N` son las sumas de diferencias positivas y negativas absolutas entre fuentes. Categorías faltantes o incompatibles producen `not_evaluable`. Es una cota inferior de las ediciones requeridas para reconciliar vectores, nunca una cota superior de incertidumbre del resultado ni un hallazgo de fraude. La proporción de blancos usa votos válidos como denominador; nulos/no marcados usa votantes; participación usa inscritos.

Las salidas de pares y espaciales son `research_preview` hasta publicar artefactos independientes de simulación. El ajuste jerárquico, diagnósticos PSIS, calibración espacial y validación independiente no están implementados por esta proyección; los reportes de API expresan la razón de inelegibilidad sin sugerir que estén completos.

## EN — Purpose and scope

This project keeps source layers separate and prioritizes records for documentary review. It does not certify results, adjudicate disputes, or replace electoral authorities. Each fact retains source type, legal status, official URL, retrieval time, hash, and transformation versions.

| Layer                             | Permitted use                                                                                                 |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Controlling final declaration     | Controls only totals and geographic scope it explicitly publishes.                                            |
| Published scrutiny                | Legally valid only within its published scope and grain; an aggregate is never forced into a final mesa fact. |
| Delegate or transmission E-14     | Documentary evidence; a non-authoritative extraction does not replace the original or an official decision.   |
| Pre-count                         | Preliminary information, not legally binding.                                                                 |
| First round and electoral history | Descriptive context only; they do not feed signals or alter results.                                          |

Reconciliation is deterministic: it validates complete canonical identities (department, municipality, polling place, and mesa), applies accounting identities only within a source, blocks rollups with duplicates, and compares only fields with compatible published grain. Coverage remains complete, missing, duplicated, or ambiguous; absence is not invented.

Mesa pre-count at this source does not publish a registered-elector denominator. It is retained as `unavailable`: turnout is not inferred, zero is not used as an observed electorate, and no unobserved-elector bound is applied. In particular, `centota=0` with positive voters is an unavailable sentinel. Statistics never contribute verified affected votes.

### Statistical-validation status

Peer, spatial, and outcome-sensitivity signals remain experimental functions. Internal verification separates at least 100 pure-null simulations from at least 100 injected alternatives, computes FDP per run, and binds family/mesa confusion and power to each run's exact code, method, cohort, and data. This implementation is not yet an independent audit and does not enable real data. It may appear only in the synthetic demonstration to exercise the contract and interface. Real releases continue to fail closed for statistics and outcome sensitivity pending a subsequent independent review. No boolean or manually asserted flag can substitute for recomputed artifacts.

### Outcome sensitivity

Outcome sensitivity is evaluated only with content-addressed source facts present in an external trust registry and affected records reviewed by two distinct authorized identities. Each review is hashed and bound to the record, exact facts, and values. Unresolved records may contribute only explicit, positive bounds observed in authenticated facts; coverage IDs must match exactly, and canonical identities prevent delimiter collisions or overlap. Margin shift uses two votes per affected vote. If any condition is missing, the status is `not_evaluable`, not an estimate. Published states distinguish robustness within evaluated bounds, a tie or lead change within the verified bound, and possibilities only when unresolved records are included. They are conditional on those bounds: they do not declare an outcome, intent, or fraud, and never turn statistical signals or history into verified affected votes.

### Review priority v1

The deterministic base takes the maximum applicable row, rather than adding rows. Statistical signals are added afterwards, capped together at 20; the total is capped at 100.

| Verifiable condition                                                           | Points |
| ------------------------------------------------------------------------------ | -----: |
| Verified accounting error **or** conflicting canonical records                 |    100 |
| Documentary difference of at least 5 votes **or** at least 2 percentage points |     70 |
| Documentary difference of 1–4 votes **and** under 2 percentage points          |     45 |
| Expected official document missing, duplicated, or ambiguous                   |     25 |
| Peer signal passing every gate                                                 |    +10 |
| Spatial signal passing every gate                                              |    +10 |

The four exhaustive public tier ranges are `documentary_review_prioritized` for 70–100, `documentary_comparison_recommended` for 45–69, `statistical_or_coverage_issue` for 15–44, and `no_review_signals` for 0–14. Read them with the components, coverage, and methodology version. A 10-point component may appear in detail even when the total remains below the review tier. There are no other public tiers.

**Permanent disclosure:** This score prioritizes records for documentary review; it does not measure or determine fraud. Absence of a signal does not prove that a mesa was error-free.

### Statistical gates

The peer model is leave-one-out empirical-Bayes beta-binomial, fitted to integer numerator/denominator counts rather than interpolated rates. One run contains exactly one complete metric/candidate family. Both the target and every peer require that metric's own denominator to be at least 80; registered electors are required only for turnout. The pool is the first level with at least 30 eligible peers: polling place, municipality, or department, always excluding the evaluated mesa and never mixing source layers, data versions, elections/rounds, or candidates. Expected ID count and digest are verified before every _p_ value and one Benjamini–Yekutieli adjustment are calculated. A signal must pass all gates: (1) two-sided EB predictive tail ≤ 0.001; (2) BY _q_ ≤ 0.05; (3) absolute standardized residual ≥ 3.5; and (4) absolute effect of at least 8 percentage points for turnout or candidate share, or 3 for blank or null/unmarked. Numerical fallbacks and large-state approximations are descriptive and never eligible for public points. It is a screening lead, not proof of error, and never estimates affected votes.

Spatial screening uses the exact hashed peer-residual artifact, not raw vote shares. Its immutable family includes release, election/round, source layer, metric, and candidate; contextual history is rejected. Coordinates require a URL, hash, accuracy, and grain. Polling-place coordinates are first collapsed to the place, so co-located mesas are not independent observations. Within each municipality it requires at least 100 eligible units, takes up to five same-municipality neighbours within 20 km (at least three; identifier breaks ties), and uses a conditional random-label null with a stable per-unit seed and at least 9,999 permutations. It adjusts every p value in the spatial family with Benjamini–Yekutieli. A positive local product is labelled a positive cluster and a negative one a spatial contrast; both are screening descriptions, never affected-vote estimates.

Benford is not used. Contextual history is not a signal. A signal does not prove an irregularity, and no signal does not prove the absence of errors.

### Anomaly review and bounded comparisons

Every declared arithmetic identity produces `pass`, `fail`, or `not_evaluable`; an unpublished field is never silently a pass. Release roll-ups require a complete, unique, exact expected identity universe for every source layer. Public anomalies remain detected (`is_anomaly`) after an explanation review. Their explanation status is one of `explained`, `partially_explained`, `no_explanation_found_in_available_data`, or `non_evaluable`; the latter is used when the preregistered review metadata or available source data is absent.

For a declared complete vector of mutually exclusive ballot categories, the minimum edit lower bound is `A_min = max(P, N)`, where `P` and `N` are the sums of positive and absolute negative cross-source category differences. Missing or incompatible categories yield `not_evaluable`. This is a lower bound on edits needed to reconcile the vectors, never an upper bound on outcome uncertainty and never a fraud finding. Blank share uses valid votes as its denominator; null/unmarked share uses voters; turnout uses registered electors.

Peer and spatial outputs are `research_preview` until independent simulation artifacts are published. Hierarchical fitting, PSIS diagnostics, spatial calibration, and independent validation are not implemented by this release projection; their API reports state the corresponding ineligibility reason rather than implying completion.
