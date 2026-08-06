import Link from "next/link";
import type { ReactNode } from "react";
import { LanguageSwitcher } from "@/components/language-switcher";
import { ScrollProgress } from "@/components/scroll-progress";
import {
  PreliminaryDisclosure,
  SyntheticDisclosure,
} from "@/components/page-primitives";
import { releaseFraming, type ReleaseFraming } from "@/lib/release-framing";

type Text = (key: string) => string;
type Locale = "es" | "en";

/** Flat-top hexagon: the wordmark glyph and the vote-field cell share a shape. */
const HEX_CLIP = "polygon(0 50%, 25% 0, 75% 0, 100% 50%, 75% 100%, 25% 100%)";

export function SiteShell({
  children,
  locale,
  t,
  framing = releaseFraming(),
}: {
  children: ReactNode;
  locale: Locale;
  t: Text;
  framing?: ReleaseFraming;
}) {
  const href = (path = "") => `/${locale}${path}`;
  const synthetic = framing === "synthetic";
  const preliminary = framing === "preliminary";

  const primary = [
    ["/resultados", t("nav.results"), t("nav.resultsDesc")],
    ["/analitica", t("nav.analytics"), t("nav.analyticsDesc")],
    ["/boletines", t("nav.bulletins"), t("nav.bulletinsDesc")],
    ["/revision", t("nav.review"), t("nav.reviewDesc")],
    ["/descargas", t("nav.downloads"), t("nav.downloadsDesc")],
  ];
  const index = [
    ...primary,
    ["/metodologia", t("nav.methodology"), t("nav.methodologyDesc")],
    ["/fuentes", t("nav.sources"), t("nav.sourcesDesc")],
    ["/api", t("footer.api"), t("nav.apiDesc")],
  ];

  return (
    <div className="min-h-screen bg-paper text-ink">
      <a
        href="#main-content"
        className="ec-field-dark sr-only z-[60] border border-neon px-4 py-3 text-meta-lg font-semibold focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        {t("common.skip")}
      </a>

      <header className="sticky top-0 z-40 border-b border-ink bg-paper supports-[backdrop-filter]:bg-paper/94 supports-[backdrop-filter]:backdrop-blur-[14px]">
        <div className="@container/shell mx-auto flex h-header max-w-[1440px] items-center justify-between gap-4 px-gutter">
          <Link
            href={href()}
            aria-label={t("site.name")}
            className="flex min-h-11 min-w-0 items-center gap-[11px] pr-1"
          >
            <span
              aria-hidden="true"
              className="block h-[15px] w-[17px] shrink-0 bg-ink"
              style={{ clipPath: HEX_CLIP }}
            />
            {/* Below @lg the glyph carries the mark alone; the link keeps its
                aria-label, so the accessible name never disappears with it. */}
            <span className="ec-mark hidden min-w-0 truncate @lg/shell:block">
              {t("site.name")}
            </span>
          </Link>

          <nav
            data-shell-navigation="desktop"
            className="hidden min-w-0 items-center @4xl/shell:flex"
            aria-label={t("nav.menu")}
          >
            {primary.map(([path, label], i) => (
              <Link
                key={path}
                href={href(path)}
                className="inline-flex min-h-11 items-center gap-2 border-b-2 border-transparent px-3 text-meta-lg hover:border-neon focus-visible:border-neon"
              >
                <span
                  aria-hidden="true"
                  className="ec-mono text-mark text-ink-4"
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                {label}
              </Link>
            ))}
          </nav>

          <div className="flex shrink-0 items-center gap-3">
            {synthetic ? (
              <a
                href="#synthetic-disclosure"
                className="ec-mono hidden border border-ink bg-neon px-2 py-1 text-mark text-ink @2xl/shell:inline-block"
              >
                {t("disclosure.syntheticChip")}
              </a>
            ) : null}
            <LanguageSwitcher locale={locale} label={t("nav.language")} />
            <details
              data-shell-navigation="compact"
              className="@4xl/shell:hidden [&[open]_.ec-index-close]:inline [&[open]_.ec-index-open]:hidden [&[open]_.ec-index-panel]:block"
            >
              <summary className="flex min-h-11 list-none items-center gap-[9px] border border-ink px-3 text-meta-lg whitespace-nowrap hover:bg-neon">
                <span aria-hidden="true" className="grid gap-[2.5px]">
                  <span className="block h-[1.5px] w-[13px] bg-ink" />
                  <span className="block h-[1.5px] w-[13px] bg-ink" />
                  <span className="block h-[1.5px] w-[13px] bg-ink" />
                </span>
                <span className="ec-index-open">{t("nav.index")}</span>
                <span className="ec-index-close hidden">
                  {t("nav.indexClose")}
                </span>
              </summary>
              <div className="ec-field-dark ec-index-panel absolute inset-x-0 top-full hidden max-h-[calc(100dvh-var(--sticky-top))] overflow-y-auto border-b border-ink">
                <nav
                  aria-label={t("nav.indexPanel")}
                  className="mx-auto grid max-w-[1440px] gap-x-8 gap-y-px px-gutter py-7 sm:grid-cols-2 lg:grid-cols-4"
                >
                  {index.map(([path, label, desc], i) => (
                    <Link
                      key={path}
                      href={href(path)}
                      /* The name is the label alone. Without this the ordinal
                         and the description join it, and every link announces
                         as a paragraph. The description still reads in browse
                         mode as the link's own content. */
                      aria-labelledby={`ec-index-${i}`}
                      className="block border-t border-rule-soft py-3.5 hover:border-neon"
                    >
                      <span
                        aria-hidden="true"
                        className="ec-mono block text-mark text-on-dark-3"
                      >
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span
                        id={`ec-index-${i}`}
                        className="mt-[7px] block text-lead leading-tight font-semibold tracking-[-.015em] text-on-dark"
                      >
                        {label}
                      </span>
                      <span className="mt-1.5 block text-meta-lg leading-[1.45] text-on-dark-2">
                        {desc}
                      </span>
                    </Link>
                  ))}
                </nav>
              </div>
            </details>
          </div>
        </div>
        <ScrollProgress />
      </header>

      {synthetic ? <SyntheticDisclosure locale={locale} t={t} /> : null}
      {preliminary ? <PreliminaryDisclosure locale={locale} t={t} /> : null}

      {children}

      <footer className="ec-field-dark mt-20">
        <div className="mx-auto grid max-w-[1440px] gap-y-10 px-gutter py-12 md:grid-cols-[minmax(0,1fr)_auto] md:gap-x-14">
          <div>
            <p className="ec-mark m-0 text-on-dark">{t("site.name")}</p>
            <p className="mt-4 max-w-[42rem] text-meta-lg leading-relaxed text-on-dark-4">
              {t("footer.mission")}{" "}
              {synthetic ? t("disclosure.synthetic") : null}
              {preliminary ? t("disclosure.preliminary") : null}
            </p>
            <p className="mt-4 text-meta-lg text-on-dark-4">
              {t("footer.madeBy")}{" "}
              <a
                href="https://octograma.com"
                target="_blank"
                rel="noopener noreferrer"
                className="border-b border-neon text-on-dark"
              >
                octograma.com
              </a>
            </p>
          </div>
          <nav
            className="grid gap-2 md:justify-items-end"
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
                className="inline-flex min-h-11 items-center text-meta-lg whitespace-nowrap text-on-dark-4 hover:text-on-dark focus-visible:text-on-dark"
              >
                {label}
              </Link>
            ))}
          </nav>
        </div>
      </footer>
    </div>
  );
}
