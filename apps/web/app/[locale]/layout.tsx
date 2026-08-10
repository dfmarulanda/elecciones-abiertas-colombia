import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "../globals.css";
import "./design.css";
import { FontPreloads } from "@/components/font-preloads";
import { SiteShell } from "@/components/site-shell";
import { publicSiteOrigin } from "@/lib/seo";

const locales = ["es", "en"] as const;

// Matches --paper in globals.css. Keep the two in step: this paints the mobile
// browser chrome, so a stale value shows as a seam above the page field.
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
  // A route must opt in through releaseMetadata after confirming the immutable
  // release is real, complete and reconciled.
  robots: { index: false, follow: false, nocache: true },
};

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!locales.includes(locale as (typeof locales)[number])) notFound();
  setRequestLocale(locale);
  const t = await getTranslations();
  return (
    <html lang={locale}>
      <head>
        <FontPreloads />
      </head>
      <body>
        <SiteShell locale={locale as "es" | "en"} t={t}>
          {children}
        </SiteShell>
      </body>
    </html>
  );
}
