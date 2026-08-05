import React, { type ReactNode } from "react";
import { Info } from "lucide-react";

export function SyntheticNotice({ locale }: { locale: "es" | "en" }) {
  return (
    <div
      className="border border-ink bg-neon px-4 py-3 text-sm leading-6 text-ink"
      role="status"
    >
      <Info className="mr-2 inline size-4" aria-hidden="true" />
      <strong>
        {locale === "es" ? "FIJACIÓN SINTÉTICA." : "SYNTHETIC FIXTURE."}
      </strong>{" "}
      {locale === "es"
        ? "Datos de desarrollo: no representan resultados electorales reales."
        : "Development data: these are not real election results."}
    </div>
  );
}

function VerifiedReleaseNotice({
  locale,
  releaseStatus,
}: {
  locale: "es" | "en";
  releaseStatus?: string;
}) {
  const candidate = releaseStatus === "candidate";
  const withdrawn = releaseStatus === "withdrawn";
  return (
    <div
      className="border border-ink bg-ink px-4 py-3 text-sm leading-6 text-paper"
      role="status"
    >
      <Info className="mr-2 inline size-4" aria-hidden="true" />
      <strong>
        {locale === "es"
          ? candidate
            ? "RELEASE CANDIDATO · LECTURA PRELIMINAR."
            : withdrawn
              ? "RELEASE RETIRADO."
              : "RELEASE INMUTABLE."
          : candidate
            ? "CANDIDATE RELEASE · PRELIMINARY READING."
            : withdrawn
              ? "WITHDRAWN RELEASE."
              : "IMMUTABLE RELEASE."}
      </strong>{" "}
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
    </div>
  );
}

export function ReleaseNotice({
  locale,
  synthetic,
  releaseStatus,
}: {
  locale: "es" | "en";
  synthetic: boolean;
  releaseStatus?: string;
}) {
  return synthetic ? (
    <SyntheticNotice locale={locale} />
  ) : (
    <VerifiedReleaseNotice locale={locale} releaseStatus={releaseStatus} />
  );
}

export function Page({
  locale,
  eyebrow,
  title,
  children,
  releaseStatus,
  synthetic = process.env.NEXT_PUBLIC_SYNTHETIC_FIXTURE === "true" ||
    !process.env.NEXT_PUBLIC_API_URL,
}: {
  locale: "es" | "en";
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
      className="mx-auto max-w-[1440px] px-[clamp(1rem,5.55vw,5rem)] py-8 sm:py-12"
    >
      <ReleaseNotice
        locale={locale}
        synthetic={synthetic}
        releaseStatus={releaseStatus}
      />
      <header className="border-b border-ink py-8 sm:py-12">
        <p className="font-mono text-xs font-bold tracking-[.14em] text-muted uppercase">
          {eyebrow}
        </p>
        <h1 className="mt-3 max-w-5xl font-display text-3xl font-bold leading-[1.06] tracking-[-0.045em] uppercase sm:text-5xl">
          {title}
        </h1>
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
    <section className="ec-editorial-section border-b border-ink py-8 first:pt-0 sm:py-10">
      <h2 className="max-w-4xl font-display text-xl font-bold leading-tight tracking-[-0.035em] uppercase sm:text-3xl">
        {title}
      </h2>
      <div className="mt-4 max-w-3xl text-sm leading-7 text-muted">
        {children}
      </div>
    </section>
  );
}
