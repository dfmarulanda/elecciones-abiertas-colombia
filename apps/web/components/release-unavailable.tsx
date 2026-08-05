import Link from "next/link";

/**
 * Shown when no standard release can be read.
 *
 * The API deliberately refuses to serve a context-only historical release
 * through the legacy release contract, because that contract cannot express
 * unknown completion without inventing values. Refusing is correct; crashing
 * on the refusal is not. An explicit unavailable state is the same discipline
 * the data layer applies to unknown, unavailable and zero.
 */
export function ReleaseUnavailable({
  locale,
  title,
  body,
  methodology,
  sources,
}: {
  locale: "es" | "en";
  title: string;
  body: string;
  methodology: string;
  sources: string;
}) {
  return (
    <main id="main-content" className="mx-auto max-w-[1440px] px-gutter py-16">
      <div className="grid max-w-5xl items-start gap-x-14 gap-y-8 border-y border-ink py-10 lg:grid-cols-[auto_minmax(0,1fr)]">
        {/* Dashed hollow hexagon: the same mark the data layer uses for
            "unavailable", so an absent release reads as absent and never as
            an empty or zeroed one. */}
        <svg
          viewBox="0 0 52 46"
          className="h-14 w-16"
          aria-hidden="true"
          focusable="false"
        >
          <path
            d="M13 1 H39 L51 23 L39 45 H13 L1 23 Z"
            fill="none"
            stroke="var(--ink-4)"
            strokeWidth="1.5"
            strokeDasharray="5 4"
          />
        </svg>
        <div>
          <h1 className="ec-head">{title}</h1>
          <p className="mt-5 max-w-[46rem] text-body leading-relaxed text-ink-2">
            {body}
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href={`/${locale}/metodologia`}
              className="inline-flex min-h-11 items-center gap-2 border border-ink px-4 text-meta-lg font-semibold hover:bg-neon"
            >
              {methodology}
            </Link>
            <Link
              href={`/${locale}/glosario`}
              className="inline-flex min-h-11 items-center gap-2 border border-ink px-4 text-meta-lg font-semibold hover:bg-neon"
            >
              {sources}
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
