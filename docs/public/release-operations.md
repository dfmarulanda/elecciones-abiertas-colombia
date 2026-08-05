# Immutable release operations / Operaciones de releases inmutables

## ES

Un release es un conjunto inmutable: manifiesto, fuentes, cobertura, artefactos, hashes, versiones de parser/transformación y versión metodológica. No se edita un release publicado para cambiar un valor. El único selector mutable es [`data/manifests/current-release.json`](../../data/manifests/current-release.json); apunta a un manifiesto cuyo nombre, `release_id` y `data_version` deben coincidir. Los objetos grandes se sirven como artefactos direccionados por contenido; el selector decide qué versión se lee.

Flujo operativo:

1. Descubrir únicamente desde entradas oficiales revisadas, preservar bytes y hash antes de analizar, y mantener identidad y condición jurídica de cada capa.
2. Crear un manifiesto candidato inmutable que contabilice cobertura, hashes y versiones. Un candidato no es una publicación.
3. Ejecutar `pnpm check:manifests`, `pnpm check:wording`, contratos, lint, tipos, pruebas y build según el flujo CI. Revisar cobertura y trazabilidad antes de cualquier activación.
4. Para un release real, exigir estado `published`, `synthetic: false` y los tres campos de gate verdaderos: `aggregate_reconciled`, `statistical_validation_passed` y `wording_validation_passed`.
5. Activar únicamente con `pnpm release:activate -- --release <immutable-release-id>`. El script se niega a activar un fixture sintético salvo con `--allow-fixture`; esa excepción es solo para desarrollo controlado.
6. Registrar quién aprobó, la evidencia de los gates, el commit y el identificador de release en el cambio revisado. Vigilar `/healthz`, `/readyz`, errores y procedencia tras activar.

**Recuperación de recolección:** los fallos de transporte y los HTTP reintentables
(`408`, `429`, `5xx`) permanecen como filas faltantes en el ledger de la corrida;
no son una declaración de que el recurso no existe. El cliente conserva
`Retry-After` y el backoff, y una reanudación explícita y revisada puede volver a
intentarlos cuando el origen se haya recuperado. Los rechazos de política, los
redireccionamientos inválidos y los HTTP terminales sí quedan en cuarentena y no
se borran por una reanudación. Nunca se aumenta la tasa ni se limpia una
cuarentena para compensar una caída del origen: se registra el incidente, se
verifica conectividad con un endpoint ya aprobado y se inicia una nueva
reanudación documentada.

**Rollback:** no se borra ni se reescribe el release problemático. Se valida el manifiesto histórico objetivo y se cambia atómicamente solo el puntero al identificador inmutable anterior mediante el mismo flujo de activación. Se documenta motivo, hora, release desde/hacia y referencia de issue. Un rollback no convierte datos antiguos en definitivos ni elimina una corrección pendiente.

Estado comprobado en el repositorio: el puntero actual selecciona `fixture-2026-round2-v1`; su manifiesto dice `status: fixture`, `synthetic: true` y `statistical_validation_passed: false`. Existe además un candidato local, nacional y no sintético, con `status: candidate`; no se activa ni publica. Tiene `aggregate_reconciled: false`, `statistical_validation_passed: false` y `wording_validation_passed: false`. Los crawls con checkpoint de ambas vueltas de 2026 siguen incompletos y el escrutinio es crudo/sin clasificar. La muestra no activa de segunda vuelta (1/14.438 puestos; 36/122.020 mesas) no demuestra cobertura ni satisface `aggregate_reconciled`. La doble digitación independiente del E-26 y los gates de conciliación, estadística/FDR, privacidad, seguridad y producto bloquean cualquier release real.

## EN

A release is an immutable set: manifest, sources, coverage, artifacts, hashes, parser/transform versions, and methodology version. A published release is not edited to change a value. The only mutable selector is [`data/manifests/current-release.json`](../../data/manifests/current-release.json); it points to a manifest whose filename, `release_id`, and `data_version` must agree. Large objects are content-addressed artifacts; the selector chooses which version is read.

Operational flow:

1. Discover only from reviewed official entry points; preserve bytes and hash before parsing, and keep every layer’s identity and legal status.
2. Create an immutable candidate manifest that accounts for coverage, hashes, and versions. A candidate is not a publication.
3. Run `pnpm check:manifests`, `pnpm check:wording`, contracts, lint, types, tests, and build through the CI flow. Review coverage and provenance before activation.
4. For a real-data release, require `published`, `synthetic: false`, and all three true gates: `aggregate_reconciled`, `statistical_validation_passed`, and `wording_validation_passed`.
5. Activate only with `pnpm release:activate -- --release <immutable-release-id>`. The script refuses a synthetic fixture unless `--allow-fixture` is supplied; that exception is for controlled development only.
6. Record approver, gate evidence, commit, and release identifier in the reviewed change. Monitor `/healthz`, `/readyz`, errors, and provenance after activation.

**Collection recovery:** transport failures and retryable HTTP responses
(`408`, `429`, `5xx`) remain missing rows in the run ledger; they do not assert
that a resource does not exist. The client honors `Retry-After` and backoff, and
an explicit, reviewed resume may retry them once the official source recovers.
Policy denials, invalid redirects, and terminal HTTP responses remain
quarantined and are not erased by a resume. Never raise the rate or clear a
quarantine to compensate for an outage: record the incident, verify one
already-approved endpoint, then start a documented new resume.

**Rollback:** do not delete or rewrite the problematic release. Validate the historic target manifest and atomically change only the pointer to the earlier immutable identifier through the same activation flow. Record reason, time, from/to releases, and issue reference. A rollback does not make older data final or erase a pending correction.

Checked-in status: the current pointer selects `fixture-2026-round2-v1`; its manifest says `status: fixture`, `synthetic: true`, and `statistical_validation_passed: false`. A local, national-only, non-synthetic candidate also exists with `status: candidate`; it is neither activated nor published. Its `aggregate_reconciled`, `statistical_validation_passed`, and `wording_validation_passed` values are all false. The checkpointed crawls for both 2026 rounds remain incomplete and scrutiny is raw/unclassified. The non-active second-round sample (1/14,438 places; 36/122,020 mesas) does not establish coverage or satisfy `aggregate_reconciled`. Independent E-26 double entry plus reconciliation, statistical/FDR, privacy, security, and product gates block every real release.
