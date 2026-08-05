import React, { type ReactNode } from "react";
import { isSyntheticFixture } from "@/lib/synthetic";

type Locale = "es" | "en";
type Text = (key: string) => string;

/**
 * Deployment-level disclosure, rendered once by SiteShell directly under the
 * sticky header on every route.
 *
 * Constraint: the fact that this build serves synthetic data must never be
 * reachable only by scrolling. It sits above the fold, above every <h1>, in the
 * same screen as the largest figure on the page, and it is a live region.
 */
export function SyntheticDisclosure({
  locale,
  t,
}: {
  locale: Locale;
  t: Text;
}) {
  return (
    <div
      id="synthetic-disclosure"
      role="status"
      lang={locale}
      className="ec-field-dark border-b border-neon"
    >
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-baseline gap-x-4 gap-y-1 px-gutter py-3.5">
        <p className="ec-mark m-0 text-neon">{t("disclosure.syntheticMark")}</p>
        <p className="m-0 max-w-[52rem] text-body leading-relaxed text-on-dark">
          {t("disclosure.synthetic")}
        </p>
      </div>
    </div>
  );
}

/**
 * Reading-level disclosure: this *release* is a fixture. Distinct from the
 * shell strip above, which is about the deployment — a live API can serve a
 * synthetic release, so the two are not the same claim and neither replaces
 * the other.
 */
export function SyntheticNotice({ locale }: { locale: Locale }) {
  return (
    <div
      className="border border-ink bg-neon px-4 py-3 text-meta-lg leading-6 text-ink"
      role="status"
    >
      <strong className="ec-mark">
        {locale === "es" ? "Fijación sintética." : "Synthetic fixture."}
      </strong>{" "}
      {locale === "es"
        ? "Esta lectura proviene de una fijación de desarrollo, no de una publicación oficial."
        : "This reading comes from a development fixture, not from an official publication."}
    </div>
  );
}

function VerifiedReleaseNotice({
  locale,
  releaseStatus,
}: {
  locale: Locale;
  releaseStatus?: string;
}) {
  const candidate = releaseStatus === "candidate";
  const withdrawn = releaseStatus === "withdrawn";
  return (
    <div
      className="ec-field-dark border border-ink px-4 py-3 text-meta-lg leading-6"
      role="status"
    >
      <strong className="ec-mark text-neon">
        {locale === "es"
          ? candidate
            ? "Release candidato · lectura preliminar."
            : withdrawn
              ? "Release retirado."
              : "Release inmutable."
          : candidate
            ? "Candidate release · preliminary reading."
            : withdrawn
              ? "Withdrawn release."
              : "Immutable release."}
      </strong>{" "}
      <span className="text-on-dark-2">
        {locale === "es"
          ? candidate
            ? "Lectura preliminar e inmutable; todavía no es una publicación final ni una conclusión oficial."
            : withdrawn
              ? "Se conserva para trazabilidad y no corresponde al release activo."
              : "Consulte la versión, la fuente y su condición jurídica en cada lectura."
          : candidate
            ? "An immutable preliminary reading; it is not a final publication or an official conclusion."
            : withdrawn
              ? "Retained for traceability; this is not the active release."
              : "Check the version, source, and legal status on every reading."}
      </span>
    </div>
  );
}

export function ReleaseNotice({
  locale,
  synthetic,
  releaseStatus,
}: {
  locale: Locale;
  synthetic: boolean;
  releaseStatus?: string;
}) {
  return synthetic ? (
    <SyntheticNotice locale={locale} />
  ) : (
    <VerifiedReleaseNotice locale={locale} releaseStatus={releaseStatus} />
  );
}

/** The 1440px column and its gutter. Every section shares this measure. */
export function Gutter({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`mx-auto max-w-[1440px] px-gutter ${className}`}>
      {children}
    </div>
  );
}

/** Small uppercase Monument label. Never below 12px, never colour-only. */
export function Eyebrow({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <p className={`ec-mark m-0 text-ink-4 ${className}`}>{children}</p>;
}

/**
 * A full-bleed dark section. `ec-field-dark` flips the surface, the ink ramp,
 * the hairline ramp and the focus ring together — an ink focus outline is
 * invisible on #151312, so the flip has to be atomic.
 */
export function FieldSection({
  id,
  label,
  children,
  className = "",
}: {
  id?: string;
  label?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      id={id}
      aria-label={label}
      className={`ec-field-dark ${className}`}
    >
      {/* Design measure: dark sections run padding:60px 0 58px at 1440px
          (mesa/proceso — conteo's own hero uses 60/54 and is handled where
          that hero is built). Compact on mobile, exact from sm up. */}
      <Gutter className="pt-12 pb-12 sm:pt-[60px] sm:pb-[58px]">
        {children}
      </Gutter>
    </section>
  );
}

/**
 * The design's recurring header pair: an eyebrow and a sentence-case heading
 * on the left, an intro paragraph on the right. Stacks below `lg`.
 */
export function SectionHeader({
  eyebrow,
  title,
  intro,
  level = 2,
  id,
}: {
  eyebrow: string;
  title: string;
  intro?: ReactNode;
  level?: 1 | 2;
  id?: string;
}) {
  const Heading = level === 1 ? "h1" : "h2";
  return (
    <div className="grid items-start gap-x-16 gap-y-5 border-t border-rule pt-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
      <div>
        <Eyebrow>{eyebrow}</Eyebrow>
        <Heading id={id} className="ec-head mt-4">
          {title}
        </Heading>
      </div>
      {intro ? (
        <div className="max-w-[44rem] text-body leading-relaxed text-ink-2">
          {intro}
        </div>
      ) : null}
    </div>
  );
}

export function Page({
  locale,
  eyebrow,
  title,
  children,
  releaseStatus,
  synthetic = isSyntheticFixture(),
}: {
  locale: Locale;
  eyebrow: string;
  title: string;
  children: ReactNode;
  synthetic?: boolean;
  releaseStatus?: string;
}) {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="mx-auto max-w-[1440px] px-gutter py-8 sm:py-12"
    >
      <ReleaseNotice
        locale={locale}
        synthetic={synthetic}
        releaseStatus={releaseStatus}
      />
      <header className="border-b border-rule py-8 sm:py-12">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="ec-head mt-4 max-w-[24ch]">{title}</h1>
      </header>
      <div className="ec-page-content py-10 sm:py-12">{children}</div>
    </main>
  );
}

export function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="ec-editorial-section border-b border-rule py-8 first:pt-0 sm:py-10">
      <h2 className="ec-head max-w-4xl text-head-sm">{title}</h2>
      <div className="mt-5 max-w-3xl text-body leading-relaxed text-ink-2">
        {children}
      </div>
    </section>
  );
}
