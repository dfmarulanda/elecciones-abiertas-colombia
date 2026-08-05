# Accessibility and privacy / Accesibilidad y privacidad

## ES — Accesibilidad

La meta es una experiencia conforme con prácticas WCAG 2.2 AA: estructura semántica, idioma de página, foco visible, navegación por teclado, controles de al menos 44 px cuando el componente lo provee, contraste legible, títulos y tablas con encabezados, y etiquetas o texto alternativo para contenido no textual. Los datos y estados se expresan en texto; color, posición o mapa no son el único canal de significado.

**Equivalente de mapa conocido:** el fixture activo no incluye coordenadas autoritativas. La interfaz no inventa ubicaciones y ofrece una tabla de geografía y número de mesas como equivalente del mapa; el motor cartográfico solo se activa cuando existan límites o coordenadas autoritativas. Esto es una limitación actual, no una afirmación de cobertura cartográfica.

Esta documentación y las páginas públicas describen las prácticas implementadas, pero no certifican una auditoría WCAG con tecnologías asistivas reales. Reporte una barrera mediante el [formulario de datos](../../.github/ISSUE_TEMPLATE/data-issue.yml), sin datos personales, indicando navegador, tecnología de asistencia, ruta y el resultado esperado.

## EN — Accessibility

The target experience follows WCAG 2.2 AA practices: semantic structure, page language, visible focus, keyboard navigation, at least 44 px controls where the component provides them, readable contrast, headings and tables with headers, and labels or alternative text for non-text content. Data and states are expressed in text; colour, position, or a map is not the only meaning channel.

**Known map equivalent:** the active fixture has no authoritative coordinates. The interface does not invent locations and supplies a geography-and-mesa-count table as the map equivalent; the map engine activates only when authoritative boundaries or coordinates exist. This is a current limitation, not a claim of map coverage.

This document and the public pages describe implemented practices, but do not certify a WCAG audit with real assistive technologies. Report a barrier through the [data issue form](../../.github/ISSUE_TEMPLATE/data-issue.yml), without personal data, including browser, assistive technology, route, and expected outcome.

## ES — Privacidad, PII y E-14

Los enlaces oficiales de E-14, E-24, E-26 y declaraciones CNE pueden indexarse con mesa canónica, URL oficial, URL/hash del índice, hora, estado y cobertura. El portal no descarga, almacena, proxifica, OCR, redacta, extrae, transcribe ni sirve archivos de elección: el original permanece exclusivamente en el sitio oficial enlazado. Las referencias relativas no se convierten en rutas de documento.

No incluya PII, acusaciones ni imágenes de formularios en reportes públicos. Para solicitar corrección, use el [formulario de GitHub](../../.github/ISSUE_TEMPLATE/data-issue.yml).

El visor no instala analítica de visitantes. Si Sentry está configurado, solo se reportan errores: el navegador envía a una ruta del mismo origen un diagnóstico limitado en tamaño que elimina parámetros de URL, correos e IP; el servidor vuelve a limitarlo y elimina usuario, cookies, cabeceras, cuerpo y consulta antes de enviarlo. El muestreo de trazas está deshabilitado.

## EN — Privacy, PII, and E-14

Official E-14, E-24, E-26, and CNE-declaration links may be indexed with canonical mesa, official URL, source-index URL/hash, timestamp, status, and coverage. The portal never downloads, stores, proxies, OCRs, redacts, extracts, transcribes, or serves election-document files: the original remains only at the linked official site. Relative references are never expanded into document paths.

Do not include PII, accusations, or form images in public reports. To request a correction, use the [GitHub form](../../.github/ISSUE_TEMPLATE/data-issue.yml).

The viewer installs no visitor analytics. When Sentry is configured, only errors are reported: the browser sends a size-bounded diagnostic to a same-origin route that removes URL parameters, email addresses, and IP addresses; the server bounds it again and removes user data, cookies, headers, bodies, and query strings before forwarding it. Trace sampling is disabled.
