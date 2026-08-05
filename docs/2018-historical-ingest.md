# Ingesta histórica presidencial 2018

Las dos vueltas de 2018 se procesan únicamente como contexto histórico. El
resultado es un candidato inactivo con `release_class: context_only`,
`source_type: contextual_baseline`, `legal_status: context_only`,
`status: candidate` y `statistical_validation_passed: false`. Ningún comando
de esta ruta cambia `current-release.json`, carga una base de datos ni publica
artefactos.

## Fuente y transferencia aprobada

Las únicas fuentes son los ZIP nacionales MMV del Observatorio de la
Registraduría:

- `MMV_NACIONAL_PRESIDENTE_2018_1v.zip`: 61,121,207 bytes, ETag
  `"6832194e-3a4a2b7"`.
- `MMV_NACIONAL_PRESIDENTE_2018_2v.zip`: 16,171,503 bytes, ETag
  `"6832194e-f6c1ef"`.

Descargue esos bytes solamente por el egreso privado autorizado. Guárdelos
primero como ficheros temporales fuera del repositorio y no los exponga por un
dominio público, proxy genérico, bucket o volumen no aprobado. Después:

```sh
uv run elecciones-pipeline historical-2018-import \
  --round-1-archive /tmp/MMV_NACIONAL_PRESIDENTE_2018_1v.zip \
  --round-2-archive /tmp/MMV_NACIONAL_PRESIDENTE_2018_2v.zip \
  --state-dir .pipeline/historical-2018
uv run elecciones-pipeline historical-2018-build \
  --state-dir .pipeline/historical-2018 \
  --release-root data/releases \
  --manifest-dir data/manifests \
  --git-commit <commit>
```

`historical-2018-import` exige ambos tamaños revisados, rechaza ZIP no válido,
miembros extra, nombres con traversal, cifrado, tamaños expandidos excesivos y
bombas de compresión. Calcula el SHA-256 completo y conserva solo el objeto
`sha256/<digest>` bajo `.pipeline/historical-2018/objects/`, que está ignorado
por Git. El parser acepta exclusivamente un CSV esperado y, antes de generar
la versión, reconcilia exactamente cada agregado con los hechos MMV.

Los conteos de mesas que aparezcan son observados en cada snapshot. La
cobertura física esperada se registra como `unknown`: nunca se infieren mesas
faltantes, ceros de candidatos/categorías ni señales de revisión.
