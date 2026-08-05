/**
 * Preload hints for the two self-hosted faces that carry first-paint text:
 * Inter Tight (headings, figures, and the body fallback on every browser that
 * refuses the Tamil Sangam .ttc) and JetBrains Mono (every id, hash and meta
 * line). Both are same-origin, which the deployment's `default-src 'self'`
 * CSP requires -- the design's fonts.googleapis.com <link> cannot be used.
 *
 * Only the latin subsets are preloaded. The latin-ext files are fetched on
 * demand by the unicode-range split in globals.css.
 */
export const FontPreloads = () => (
  <>
    <link
      rel="preload"
      href="/fonts/inter-tight-latin.woff2"
      as="font"
      type="font/woff2"
      crossOrigin="anonymous"
    />
    <link
      rel="preload"
      href="/fonts/jetbrains-mono-latin.woff2"
      as="font"
      type="font/woff2"
      crossOrigin="anonymous"
    />
  </>
);
