/** Server-rendered JSON-LD. Values are serialized and `<`-escaped by lib/seo. */
export function SeoStructuredData({ value }: { value: string | null }) {
  if (!value) return null;
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: value }}
    />
  );
}
