import Link from "next/link";
import { Menu, MoveUpRight } from "lucide-react";
import type { ReactNode } from "react";
import { LanguageSwitcher } from "@/components/language-switcher";

type Text = (key: string) => string;
type Locale = "es" | "en";

export function SiteShell({
  children,
  locale,
  t,
}: {
  children: ReactNode;
  locale: Locale;
  t: Text;
}) {
  const href = (path = "") => `/${locale}${path}`;
  const links = [
    ["/resultados", t("nav.results")],
    ["/analitica", t("nav.analytics")],
    ["/boletines", t("nav.bulletins")],
    ["/revision", t("nav.review")],
    ["/descargas", t("nav.downloads")],
  ];
  return (
    <div className="min-h-screen bg-paper text-ink">
      <a
        href="#main-content"
        className="sr-only z-[60] border border-ink bg-neon px-4 py-3 font-semibold text-ink focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        {t("common.skip")}
      </a>
      <header className="sticky top-0 z-40 h-[72px] border-b border-ink bg-paper supports-[backdrop-filter]:bg-paper/90 supports-[backdrop-filter]:backdrop-blur-[12px]">
        <div className="@container/shell mx-auto flex h-full max-w-[1440px] items-center justify-between gap-3 px-[clamp(1rem,5.55vw,5rem)]">
          <Link
            href={href()}
            aria-label={t("site.name")}
            className="group flex min-h-11 min-w-0 items-center gap-3 pr-2"
          >
            <span className="grid size-9 shrink-0 place-content-center border border-ink bg-ink font-mono text-xs font-black tracking-[.08em] text-paper">
              EC
            </span>
            <span className="hidden min-w-0 @2xl/shell:block">
              <span className="block truncate font-display text-sm font-bold leading-none tracking-[-0.04em] uppercase">
                {t("site.name")}
              </span>
              <span className="mt-1 hidden font-mono text-[10px] font-semibold tracking-[.12em] text-muted uppercase @4xl/shell:block">
                {t("site.tagline")}
              </span>
            </span>
          </Link>
          <nav
            data-shell-navigation="desktop"
            className="hidden items-center gap-1 @4xl/shell:flex"
            aria-label={t("nav.menu")}
          >
            {links.map(([path, label], index) => (
              <Link
                className="inline-flex min-h-11 items-center gap-2 border-l border-transparent px-3 text-xs font-semibold uppercase hover:border-ink hover:bg-neon"
                href={href(path)}
                key={path}
              >
                <span
                  aria-hidden="true"
                  className="font-mono text-[10px] text-muted"
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                {label}
              </Link>
            ))}
          </nav>
          <div className="flex shrink-0 items-center gap-2">
            <LanguageSwitcher locale={locale} label={t("nav.language")} />
            <details
              data-shell-navigation="compact"
              className="relative @4xl/shell:hidden"
            >
              <summary className="flex min-h-11 list-none items-center gap-2 border border-ink bg-paper px-3 text-sm font-semibold hover:bg-neon">
                <Menu className="size-4" aria-hidden="true" />
                <span className="sr-only">{t("nav.menu")}</span>
              </summary>
              <nav
                className="absolute right-0 z-40 mt-2 w-64 border border-ink bg-paper p-2"
                aria-label={t("nav.menu")}
              >
                {links.map(([path, label], index) => (
                  <Link
                    className="flex min-h-11 items-center gap-3 border-l border-transparent px-3 text-sm font-semibold hover:border-ink hover:bg-neon"
                    href={href(path)}
                    key={path}
                  >
                    <span
                      aria-hidden="true"
                      className="font-mono text-[10px] text-muted"
                    >
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    {label}
                  </Link>
                ))}
              </nav>
            </details>
          </div>
        </div>
      </header>
      {children}
      <footer className="mt-16 border-t border-ink bg-ink text-paper">
        <div className="mx-auto grid max-w-[1440px] gap-8 px-[clamp(1rem,5.55vw,5rem)] py-10 md:grid-cols-[1fr_auto]">
          <div>
            <p className="font-display text-sm font-bold uppercase">
              {t("site.name")}
            </p>
            <p className="mt-2 max-w-xl text-sm leading-6 text-paper/75">
              {t("footer.rights")}
            </p>
          </div>
          <nav
            className="flex flex-wrap gap-x-5 gap-y-2 text-sm"
            aria-label={t("footer.navigation")}
          >
            {[
              ["/metodologia", t("nav.methodology")],
              ["/fuentes", t("nav.sources")],
              ["/glosario", t("footer.glossary")],
              ["/accesibilidad", t("footer.accessibility")],
              ["/privacidad", t("footer.privacy")],
              ["/api", t("footer.api")],
            ].map(([path, label]) => (
              <Link
                key={path}
                href={href(path)}
                className="inline-flex min-h-11 items-center gap-1 underline decoration-paper/40 underline-offset-4 hover:decoration-paper"
              >
                {label}
                <MoveUpRight className="size-3" aria-hidden="true" />
              </Link>
            ))}
          </nav>
        </div>
      </footer>
    </div>
  );
}
