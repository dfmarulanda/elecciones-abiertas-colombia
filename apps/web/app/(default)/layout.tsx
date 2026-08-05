import type { Metadata } from "next";
import "../globals.css";
import { publicSiteOrigin } from "@/lib/seo";

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
      <body>{children}</body>
    </html>
  );
}
