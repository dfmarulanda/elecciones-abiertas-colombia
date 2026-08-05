# Deployment runbook / Runbook de despliegue

## ES

Este es un runbook de entrega y operación. Estado verificado el 4 de agosto de
2026: existe únicamente un `collector` privado temporal en Railway para
egress controlado. No tiene dominio público, volumen ni bucket; la web, la API,
Neon y R2 todavía no están desplegados en producción. Use los nombres de
variables listados a continuación; configure sus valores solo en el gestor de
secretos de cada plataforma y nunca en commits, issues, logs, capturas o
documentación pública.

| Componente                     | Destino previsto | Variables por nombre                                                                                                                                           |
| ------------------------------ | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Web Next.js                    | Vercel           | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_ELECTION_SLUG`, `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_ACTIVE_RELEASE`, `NEXT_PUBLIC_SYNTHETIC_FIXTURE`                    |
| API FastAPI                    | Railway          | `DATABASE_URL`, `ELECCIONES_SENTRY_DSN`, `CURSOR_SECRET`, `ACTIVE_RELEASE`, `ACTIVE_RELEASE_POINTER`, `FIXTURE_DATA_PATH`, `ALLOWED_ORIGINS`, `ARTIFACT_HOSTS` |
| Read model                     | Neon PostgreSQL  | `DATABASE_URL`                                                                                                                                                 |
| Objetos de pipeline/artefactos | Cloudflare R2    | `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_BASE_URL`                                                               |
| Observabilidad                 | Sentry           | `SENTRY_DSN`, `ELECCIONES_SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN`                                                                                                |
| Recolección programada         | GitHub Actions   | `OFFICIAL_SOURCE_HOSTS`, `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`                                                            |

1. En GitHub Actions, ejecute CI antes de promoción: generación de contratos, validación de manifiestos y lenguaje, lint, tipos, pruebas y build. El workflow de fuentes programado debe comparar manifiestos y no publicar automáticamente.
2. En Neon, provisionar una base PostgreSQL compatible, ejecutar migraciones revisadas y cargar únicamente un release inmutable validado. La API rechaza modo base de datos si `CURSOR_SECRET` conserva el valor de desarrollo.
3. En R2, usar un bucket para JSON estructurado y artefactos inmutables. No almacenar PDFs, copias, OCR ni derivados de E-14/E-24/E-26/CNE; publicar únicamente datasets y permitir redirecciones de dataset a hosts HTTPS de `ARTIFACT_HOSTS`.
4. En Railway, construir desde `apps/api/Dockerfile`, usar `/healthz` para health check y `/readyz` para disponibilidad de lectura. Definir `ALLOWED_ORIGINS` con orígenes explícitos de la web. Mantener la API de solo lectura.
5. En Vercel, desplegar `apps/web`, establecer `NEXT_PUBLIC_API_URL` hacia la API elegida y mantener visible el estado sintético cuando aplique. La configuración incluida añade `X-Content-Type-Options` y política de referente.
6. En Sentry, habilitar solo los DSN correspondientes y verificar que eventos no incluyan PII, cuerpos de actas o valores secretos. La web envía fallos del navegador mediante la ruta interna, limitada y de mismo origen, `/api/_monitoring/client-error`; no es un endpoint de datos electorales.
7. Tras desplegar, consultar `/healthz`, `/readyz`, una respuesta con procedencia y `ETag`, y el contrato `/api/v1/openapi.json`. Después de un cambio de release, verificar que `data_version` cambió al identificador esperado y que no se sirvió fixture como dato electoral real.

### Recolección por relay privado de egress controlado

La implementación operativa conserva los objetos y checkpoints en la máquina
local y usa esta ruta cerrada:

`crawler local → 127.0.0.1:18787 → túnel SSH Railway → relay 127.0.0.1:8787 → hosts oficiales permitidos`

El relay está fijado a una sola región de nube (`us-west2`), pero **esto no es
una IP de salida estática**. Railway reserva static outbound IP para Pro. No se
usa Vercel como proxy, no hay ingress ni dominio público, y no se usan VPNs,
proxies rotativos, rotación de IP, reescritura DNS o rutas inferidas. El relay
acepta solo identidades tipadas para JSON oficial de 2026 y ZIP tabular oficial
de 2018/2022; no expone una URL arbitraria ni ruta alguna para PDF o documento
electoral.

La sonda de arranque verificó el `config.json` de segunda vuelta con estado
200, `application/json`, 931 bytes y SHA-256
`6cf56876f26e690bce28ba4d19d190f0fe6f67e5b68c2d2bbf064ac5d3d7ab5f`.
Antes de la reanudación, el smoke test de cada vuelta confirmó 10 respuestas
condicionales 304, procedencia oficial intacta, una falla recuperable y ninguna
modificación de cuarentena. El límite está implementado dentro del relay: dos
conexiones globales y 2 solicitudes por segundo por host.

#### Estado operativo

Ejecute desde la raíz del repositorio. El directorio temporal actual contiene
el token, la clave y el PID del túnel; nunca imprima ni pase el token en la
línea de comandos.

```sh
RELAY_RUNTIME_DIR=/tmp/elections-railway-relay.lDX63I
for round in 1 2; do
  state_dir=".pipeline/official-2026-round${round}"
  crawl_pid="$(tr -d '\n' < "$state_dir/mesas-relay-resume.pid")"
  ps -p "$crawl_pid" -o pid=,ppid=,pgid=,stat=,%cpu=,%mem=,rss=,etime=,command=
  tail -n 8 "$(ls -t "$state_dir"/logs/mesas-relay-resume-*.log | head -n 1)"
  sqlite3 "$state_dir/checkpoints.sqlite3" 'SELECT COUNT(*) FROM quarantine;'
done
tunnel_pid="$(tr -d '\n' < "$RELAY_RUNTIME_DIR/tunnel.pid")"
ps -p "$tunnel_pid" -o pid=,ppid=,pgid=,stat=,etime=,command=
lsof -nP -iTCP:18787 -sTCP:LISTEN
railway status --json
railway logs --since 15m --filter relay_request
railway logs --network --since 15m --direction egress --status dropped
```

Un PID no basta: `STAT` no debe contener `T`, los contadores del log deben
crecer y el puerto debe seguir enlazado solo a `127.0.0.1`. La cuarentena base
es 44 en cada vuelta; cualquier aumento requiere revisión. Una base ocupada se
vuelve a consultar después, sin tratar el bloqueo como una falla de datos.

#### Detener y reanudar sin perder estado

Detenga primero los crawlers con `SIGINT` para permitir cierre y commit. Si
alguno está pausado (`T`), reanúdelo antes de enviar `SIGINT`. No detenga el
túnel ni Railway hasta que ambos procesos hayan terminado.

```sh
for round in 1 2; do
  state_dir=".pipeline/official-2026-round${round}"
  crawl_pid="$(tr -d '\n' < "$state_dir/mesas-relay-resume.pid")"
  case "$(ps -p "$crawl_pid" -o stat=)" in *T*) kill -CONT "$crawl_pid" ;; esac
  kill -INT "$crawl_pid"
  while ps -p "$crawl_pid" >/dev/null 2>&1; do sleep 2; done
done
```

Antes de reanudar, confirme que el relay y el túnel están sanos, archive cada
PID file obsoleto solo después de probar que su PID ya no existe y ejecute los
dos smoke tests. El token se referencia únicamente mediante el archivo modo 0600.

```sh
for round in 1 2; do
  pid_file=".pipeline/official-2026-round${round}/mesas-relay-resume.pid"
  old_pid="$(tr -d '\n' < "$pid_file")"
  if ps -p "$old_pid" >/dev/null 2>&1; then exit 1; fi
  mv "$pid_file" "$pid_file.stopped-$(date -u +%Y%m%dT%H%M%SZ)"
done
.venv/bin/elecciones-pipeline precount-relay-smoke --round 1 \
  --state-dir .pipeline/official-2026-round1 \
  --relay-base-url http://127.0.0.1:18787 \
  --relay-token-file "$RELAY_RUNTIME_DIR/token"
.venv/bin/elecciones-pipeline precount-relay-smoke --round 2 \
  --state-dir .pipeline/official-2026-round2 \
  --relay-base-url http://127.0.0.1:18787 \
  --relay-token-file "$RELAY_RUNTIME_DIR/token"
.venv/bin/python -m elecciones_pipeline.ops.launch_relay_resume --round 1 \
  --relay-base-url http://127.0.0.1:18787 \
  --relay-token-file "$RELAY_RUNTIME_DIR/token"
.venv/bin/python -m elecciones_pipeline.ops.launch_relay_resume --round 2 \
  --relay-base-url http://127.0.0.1:18787 \
  --relay-token-file "$RELAY_RUNTIME_DIR/token"
```

#### Limpieza, solo después de completar o detener ambas vueltas

Verifique primero que no quede ningún crawler y que ambos SQLite respondan
`ok` a `PRAGMA quick_check`. Después, en este orden: termine el PID de
`tunnel.pid`, elimine la variable `COLLECTOR_RELAY_TOKEN` mediante `railway
variable delete` sin listar su valor, ejecute `railway down --service collector
--environment production --yes`, retire la clave temporal con `railway ssh
keys remove` usando su fingerprint y borre únicamente el directorio temporal
validado. No borre `.pipeline/official-2026-round*`: allí están el estado
reanudable, los objetos inmutables y la procedencia.

```sh
for round in 1 2; do
  sqlite3 ".pipeline/official-2026-round${round}/checkpoints.sqlite3" \
    'PRAGMA quick_check;'
  sqlite3 ".pipeline/official-2026-round${round}/crawl.sqlite3" \
    'PRAGMA quick_check;'
done
tunnel_pid="$(tr -d '\n' < /tmp/elections-railway-relay.lDX63I/tunnel.pid)"
kill -TERM "$tunnel_pid"
while ps -p "$tunnel_pid" >/dev/null 2>&1; do sleep 1; done
railway variable delete COLLECTOR_RELAY_TOKEN \
  --service collector --environment production
railway down --service collector --environment production --yes
railway ssh keys remove \
  'SHA256:gNCwgvh4+KEEF37jOc82gLhGXBm3kvOjBmhLLl4uBxE'
if [ "$(realpath /tmp/elections-railway-relay.lDX63I)" != \
  /tmp/elections-railway-relay.lDX63I ]; then
  exit 1
fi
find /tmp/elections-railway-relay.lDX63I -depth -delete
```

Rollback de aplicación: revierta la implementación mediante el mecanismo auditable de la plataforma y confirme probes. Rollback de datos: siga [operaciones de releases](release-operations.md); cambie solo el puntero a un release inmutable validado. Ningún rollback debe borrar objetos, manifiestos ni registros de correcciones.

## EN

This is a delivery and operations runbook. Verified state on August 4, 2026:
only a temporary private Railway `collector` exists for controlled egress. It
has no public domain, volume, or bucket; the production web, API, Neon, and R2
deployments do not yet exist. Credentials and edge controls remain operator
gates. Use the variable names listed above and keep values out of commits,
issues, logs, screenshots, and public documentation.

The table maps Web to Vercel, API to Railway, the PostgreSQL read model to Neon, pipeline/artifacts to Cloudflare R2, monitoring to Sentry, and scheduled collection to GitHub Actions. Follow the seven ES steps: run CI gates; provision/migrate Neon with a non-development cursor secret; keep structured JSON and immutable R2 objects separated from election-document PDFs (which are never stored); deploy a read-only Railway API with explicit CORS and probes; deploy Vercel with a selected API and synthetic-state visibility; prevent PII in Sentry; then verify probes, provenance, `ETag`, frozen OpenAPI, and expected `data_version`.

### Collection through the private controlled-egress relay

The live arrangement keeps immutable objects and SQLite checkpoints locally
and forwards only typed requests through an SSH tunnel to a loopback-only
Railway relay. It is pinned to one cloud region, not a fixed/static outbound
IP; Railway static outbound IP requires Pro. There is no public ingress,
domain, volume, or bucket. Arbitrary URLs and every PDF/document route are
absent. The Spanish section above is the canonical status, stop, gated-resume,
and cleanup procedure. Its commands never expose the bearer token: only an
owner-readable token-file path is passed. Keep the relay, tunnel, temporary SSH
key, and Railway service alive until both crawls finish or have been gracefully
stopped and their databases verified.

Application rollback uses the platform’s auditable mechanism and probe verification. Data rollback follows [release operations](release-operations.md): change only the pointer to a validated immutable release. Never delete objects, manifests, or correction records as part of rollback.
