import { getSeoSitemapCatalog, sitemapUrls, xml } from "@/lib/seo-sitemap";

export const revalidate = 3600;
export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ partition: string }> },
) {
  const { partition } = await params;
  const valid =
    partition === "national" ||
    partition === "departments" ||
    /^municipalities-\d+$/.test(partition);
  if (!valid) return new Response("Not found", { status: 404 });
  const catalog = await getSeoSitemapCatalog().catch(() => null);
  const urls = sitemapUrls(
    catalog,
    partition as "national" | "departments" | `municipalities-${number}`,
  );
  if (!urls.length && partition !== "national")
    return new Response("Not found", { status: 404 });
  const body = urls
    .map(
      (item) =>
        `<url><loc>${xml(item.loc)}</loc><lastmod>${xml(item.lastmod)}</lastmod></url>`,
    )
    .join("");
  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${body}</urlset>`,
    {
      headers: {
        "Content-Type": "application/xml; charset=utf-8",
        "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
      },
    },
  );
}
