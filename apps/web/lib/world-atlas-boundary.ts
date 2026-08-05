/**
 * Provenance for the vendored world map geometry used by the coverage map.
 *
 * The design (`mapa-cobertura.html`) fetches this file at runtime from
 * `https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json`. The
 * app's CSP has no CDN in `script-src`/`connect-src`, so the exact same file
 * is vendored at `/public/maps/countries-110m.json` and fetched same-origin
 * instead — same bytes, same version, just a different host.
 */
export const WORLD_ATLAS_BOUNDARY = {
  version: "world-atlas@2.0.2 · countries-110m (Natural Earth 1:110m cultural)",
  sourceUrl:
    "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json",
  vendoredPath: "/maps/countries-110m.json",
  vendoredSha256:
    "2516c915867c7baf18ddec727aec46c315541a07cfb3d79a6559b05d5e94eee8",
  attribution: "Natural Earth (public domain), packaged by world-atlas",
} as const;
