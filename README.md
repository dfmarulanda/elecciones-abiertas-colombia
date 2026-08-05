# Elecciones Abiertas Colombia

## Qué es esto

Una infraestructura abierta para que cualquier persona pueda **verificar por sí misma** los resultados electorales de Colombia, en lugar de tener que confiar en un resumen publicado por un tercero.

El proyecto recolecta datos de las fuentes oficiales de la Registraduría y el CNE, conserva los bytes crudos con su hash y su fecha de recuperación, y expone cada cifra junto con su procedencia: de qué URL salió, cuándo, bajo qué versión de parser y con qué condición jurídica. Todo release es inmutable y reproducible; revertir es cambiar un puntero.

El principio central es que **el preconteo preliminar, la evidencia documental E-14 y el escrutinio con validez jurídica son capas distintas y nunca se mezclan silenciosamente**. Un número preliminar no se presenta como un resultado legal, y un documento escaneado no se presenta como un dato verificado.

## Qué NO es esto

- **No es una acusación de fraude.** El proyecto calcula un **puntaje de prioridad de auditoría**, que solo ordena registros para revisión humana. No es una probabilidad de fraude, no es un hallazgo y no sustituye la evidencia documental ni una conclusión jurídica. El repositorio incluye un gate automatizado que bloquea ese tipo de redacción en las páginas públicas.
- **No publica resultados oficiales de 2026.** El puntero activo selecciona un conjunto **sintético** explícitamente marcado. Ningún release real de 2026 es publicable todavía.
- **No es una fuente oficial.** Las fuentes oficiales son la Registraduría y el CNE, y siempre se enlazan como originales.
- **No descarga ni transcribe formularios E-14.** El manejo es solo de índice: se registra la referencia externa y su procedencia, nunca el PDF, ni copia, ni OCR, ni derivados.

## What this is

Open infrastructure that lets anyone **verify Colombian election results for themselves**, instead of trusting a summary published by someone else.

It collects data from the official Registraduría and CNE sources, preserves the raw bytes with their hash and retrieval timestamp, and publishes every figure alongside its provenance: which URL it came from, when, under which parser version, and with what legal status. Releases are immutable and reproducible; a rollback is a pointer change.

The core principle is that **preliminary pre-count, E-14 documentary evidence, and legally valid scrutiny are separate layers that never silently substitute for one another**.

## What this is NOT

- **Not an accusation of fraud.** It computes an **audit-priority score** that only ranks records for human review. It is not a fraud probability, not a finding, and never replaces documentary evidence or a legal conclusion. An automated gate blocks that wording from reader-facing pages.
- **Not a publication of real 2026 results.** The active pointer selects an explicitly marked **synthetic** fixture.
- **Not an official source.** The Registraduría and CNE are; their originals are always linked.
- **Not an E-14 document mirror.** Handling is index-only: the external reference and its provenance are recorded, never the PDF, a cache, OCR, or any derivative.

---

Visor público, bilingüe y reproducible de resultados electorales de Colombia. La arquitectura mantiene separados el preconteo preliminar, la evidencia documental E-14 y el escrutinio con validez jurídica; ninguna capa reemplaza silenciosamente a otra.

> El puntero público activo selecciona `fixture-2026-round2-v1`, un conjunto **sintético** explícitamente marcado. No representa resultados oficiales de 2026 ni debe presentarse como una publicación electoral real.

Los crawls con checkpoint de 2026 (primera y segunda vuelta) continúan incompletos. La primera vuelta de escrutinio sí completó la recuperación cruda de sus 23.828 recursos oficiales y una clasificación de esquemas solo de metadatos: conserva 118.343 referencias documentales explícitas con procedencia, pero produce **cero** hechos de resultados electorales. No sigue referencias, no OCRiza E-14 y no constituye escrutinio parseado, declaración final ni publicación jurídica. El escrutinio de segunda vuelta sigue como bytes crudos/en progreso. Un candidato local no sintético, solo nacional, no está publicado ni activo. La doble digitación humana independiente del E-26, cobertura, conciliación, validación estadística/FDR, privacidad y gates de producto siguen bloqueando toda publicación real de 2026. La muestra no activa de segunda vuelta (1/14.438 puestos; 36/122.020 mesas) es solo una comprobación aritmética local, no conciliación ni cobertura nacional. No hay un release real de 2026 publicable.

Como contexto histórico, ambos ZIP oficiales MMV de 2022 están extraídos íntegramente en el candidato no activo `historical-2022-mmv-context-v2-705d3d71523003b8`, con tipo `contextual_baseline` y estado jurídico `context_only`. Contiene 1.125.896 filas crudas, 1.349.277 rollups y 241.652 nodos geográficos; cada ronda observa 103.364 mesas, 34 códigos de departamento/exterior, 1.188 municipios, 2.978 zonas y 13.261 puestos. Es una cobertura observada del snapshot, no una afirmación de completitud frente a un denominador independiente de mesas esperadas. No se inventan coordenadas de puestos o mesas.

## Arquitectura

- `apps/web`: Next.js 16, App Router, `next-intl`, Tailwind, Radix/shadcn patterns, TanStack y MapLibre.
- `apps/api`: FastAPI, SQLAlchemy 2, Alembic y PostgreSQL; ofrece una lectura inmutable y paginada.
- `pipeline`: recolección reiniciable, documentos, normalización, conciliación, analítica y publicación.
- `packages/contracts`: OpenAPI, cliente TypeScript generado, enumeraciones y JSON Schema.
- `data/manifests`: puntero de release activo y manifiestos pequeños. Los objetos grandes pertenecen a R2.

El puntero [`data/manifests/current-release.json`](data/manifests/current-release.json) selecciona una versión inmutable. Un rollback solo cambia ese puntero.

## Requisitos

- Node.js 22
- pnpm 11.1.3
- Python 3.13
- uv 0.11.3

```bash
pnpm install
uv sync --all-packages
pnpm contracts:generate
pnpm dev
```

La web queda en `http://localhost:3000` y la API en `http://localhost:8000`.

## Verificación

```bash
pnpm verify
pnpm test:e2e
```

Los gates verifican manifiestos, cobertura, trazabilidad, redacción neutral, contratos, tipos, pruebas y builds. Un release real no se publica automáticamente al detectar cambios de origen.

## Fuentes y límites

Cada hecho público incluye versión, tipo y condición jurídica de la fuente, URL oficial, fecha de recuperación, hash SHA-256 y versiones de parser/transformación. Los valores cero, desconocidos y no disponibles son estados distintos. La verificación de robots, términos y uso permitido sigue pendiente; los límites técnicos de recolección no sustituyen esa revisión.

En los datos de mesa de este preconteo no está disponible el denominador de electores inscritos; por ello no se infiere participación ni se convierte un valor ausente en cero. En particular, `centota=0` con votantes positivos es un centinela de no disponibilidad, no un cero observado. Las estadísticas nunca aportan votos afectados verificados.

El **puntaje de prioridad de auditoría** organiza registros para revisión. Nunca sustituye la evidencia documental ni constituye una conclusión jurídica.

## Licencia

Copyright © 2026 contributors. Código disponible bajo [GNU Affero General Public License v3.0](LICENSE), exclusivamente (`AGPL-3.0-only`). Los datos de terceros conservan sus condiciones y atribuciones de origen.
