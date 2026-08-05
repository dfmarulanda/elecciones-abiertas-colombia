import { publicSiteOrigin } from "@/lib/seo";
import {
  getSeoSitemapCatalog,
  sitemapPartitions,
  xml,
} from "@/lib/seo-sitemap";

export const revalidate = 3600;
// Keep publication discovery out of the build; immutable API reads are cached
// by getSeoSitemapCatalog and refreshed through ISR at runtime.
export const dynamic = "force-dynamic";

export async function GET() {
  const origin = publicSiteOrigin();
  const catalog = await getSeoSitemapCatalog().catch(() => null);
  const body = sitemapPartitions(catalog)
    .map(
      (partition) =>
        `<sitemap><loc>${xml(`${origin}/sitemaps/${partition}.xml`)}</loc><lastmod>${xml(catalog!.lastmod)}</lastmod></sitemap>`,
    )
    .join("");
  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${body}</sitemapindex>`,
    {
      headers: {
        "Content-Type": "application/xml; charset=utf-8",
        "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
      },
    },
  );
}
