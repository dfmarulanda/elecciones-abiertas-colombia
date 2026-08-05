import Link from "next/link";
import { CircleSlash } from "lucide-react";

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
    <main
      id="main-content"
      className="mx-auto max-w-[1440px] px-[clamp(1rem,5.55vw,5rem)] py-16"
    >
      <div className="max-w-4xl border-y border-ink py-7 sm:py-10">
        <CircleSlash className="size-10 text-muted" aria-hidden="true" />
        <h1 className="mt-6 font-display text-3xl font-bold tracking-[-0.045em] uppercase sm:text-5xl">
          {title}
        </h1>
        <p className="mt-4 max-w-xl leading-7 text-muted">{body}</p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href={`/${locale}/metodologia`}
            className="inline-flex min-h-11 items-center gap-2 border border-ink px-4 text-sm font-bold hover:bg-neon"
          >
            {methodology}
          </Link>
          <Link
            href={`/${locale}/glosario`}
            className="inline-flex min-h-11 items-center gap-2 border border-ink px-4 text-sm font-bold hover:bg-neon"
          >
            {sources}
          </Link>
        </div>
      </div>
    </main>
  );
}
