import type { Metadata, Viewport } from "next";
import "../globals.css";
import { FontPreloads } from "@/components/font-preloads";
import { publicSiteOrigin } from "@/lib/seo";

// Mirrors app/[locale]/layout.tsx. This route group owns its own <html>, so a
// token or font change made only in the locale layout silently misses it.
export const viewport: Viewport = {
  themeColor: "#f4f1ea",
  colorScheme: "light",
};

export const metadata: Metadata = {
  metadataBase: publicSiteOrigin() ? new URL(publicSiteOrigin()!) : undefined,
  title: {
    default: "Elecciones Abiertas Colombia",
    template: "%s · Elecciones Abiertas Colombia",
  },
  description:
    "Visor público, bilingüe y reproducible de resultados electorales de Colombia.",
  robots: { index: false, follow: false, nocache: true },
};

export default function DefaultRootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <head>
        <FontPreloads />
      </head>
      <body>{children}</body>
    </html>
  );
}
