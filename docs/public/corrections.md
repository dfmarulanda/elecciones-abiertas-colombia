# Corrections / Correcciones

## ES

Una diferencia entre fuentes no es por sí misma una corrección. Se clasifica como corrección oficial solo cuando un cambio dentro de la misma fuente, para la misma identidad canónica, lleva un marcador oficial de corrección. Un cambio sin ese marcador queda como revisión no marcada; una diferencia entre capas sigue siendo diferencia entre fuentes. La evidencia documental organiza revisión y no adjudica el hecho.

Para solicitar revisión pública, abra el formulario de GitHub [`Reportar un problema de datos / Report a data issue`](../../.github/ISSUE_TEMPLATE/data-issue.yml). Incluya versión de datos, mesa o ámbito, capa de fuente, URL oficial y campo/valores observados. El formulario exige confirmar que no contiene datos personales ni acusaciones. No publique nombres de jurados, firmas, identificaciones, imágenes no redactadas ni conclusiones sobre personas.

Proceso:

1. Confirmar que la URL es oficial y permitida, y preservar el reporte recibido.
2. Comparar identidad, granularidad, condición jurídica, fecha, hash y valores sin mezclar capas.
3. Clasificar: `unchanged`, `official_correction`, `unmarked_revision`, `cross_source_difference` o `incompatible_identity`.
4. Si corresponde, crear un nuevo release inmutable y un manifiesto con cobertura/procedencia completa; nunca modificar el release anterior.
5. Añadir una entrada inmutable al registro de correcciones, enlazar el issue y activar solo si el nuevo release satisface sus gates.

### Formato de registro inmutable

Guarde una entrada por corrección en un artefacto versionado/append-only asociado al release nuevo. No reutilice ni edite una entrada previamente publicada. El siguiente JSON es el formato mínimo propuesto; los valores entre ángulos son marcadores, no datos reales.

```json
{
  "correction_id": "corr-<immutable-id>",
  "recorded_at": "<ISO-8601 timestamp>",
  "status": "official_correction|unmarked_revision|cross_source_difference|incompatible_identity|unchanged",
  "supersedes_release_id": "<immutable-release-id>",
  "replacement_release_id": "<immutable-release-id>",
  "issue_path": ".github/ISSUE_TEMPLATE/data-issue.yml",
  "issue_reference": "<GitHub issue URL or number>",
  "scope": { "mesa_id": "<canonical mesa id>", "field": "<field>" },
  "source": {
    "source_type": "<source type>",
    "legal_status": "<legal status>",
    "official_url": "<verified HTTPS URL>",
    "previous_content_hash": "<SHA-256 or null>",
    "replacement_content_hash": "<SHA-256 or null>"
  },
  "reason": {
    "es": "<descripción verificable>",
    "en": "<verifiable description>"
  },
  "evidence": ["<official URL or immutable artifact reference>"],
  "approved_by": "<maintainer role or reviewed change reference>",
  "privacy_review": "no_public_pii"
}
```

## EN

A difference between sources is not automatically a correction. It is `official_correction` only when a change within the same source and canonical identity carries an official correction marker. A change without that marker is `unmarked_revision`; a difference across layers remains `cross_source_difference`. Documentary evidence organizes review and does not adjudicate the fact.

To request public review, open the GitHub [`Report a data issue / Reportar un problema de datos`](../../.github/ISSUE_TEMPLATE/data-issue.yml) form. Include data version, mesa or scope, source layer, official URL, and observed field/values. The form requires confirmation that it contains no personal data or accusations. Do not publish juror names, signatures, identification numbers, unredacted images, or conclusions about people.

Follow the five ES steps above: verify the official allowlisted URL and preserve the report; compare identity, grain, legal status, time, hash, and values without mixing layers; classify the change; create a new immutable release if warranted; append the correction-log entry and activate only after release gates. The JSON format is bilingual by field and is the durable minimum record.
