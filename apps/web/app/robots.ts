import type { MetadataRoute } from "next";

import { publicSiteOrigin } from "@/lib/seo";

export default function robots(): MetadataRoute.Robots {
  const origin = publicSiteOrigin();
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/api/", "/actas/"] }],
    sitemap: origin ? `${origin}/sitemap.xml` : undefined,
  };
}
