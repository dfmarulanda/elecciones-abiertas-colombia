import Link from "next/link";
import { ArrowLeft, Construction } from "lucide-react";

export function PlaceholderPage({
  locale,
  title,
  body,
  back,
}: {
  locale: "es" | "en";
  title: string;
  body: string;
  back: string;
}) {
  return (
    <main
      id="main-content"
      className="mx-auto max-w-[1440px] px-[clamp(1rem,5.55vw,5rem)] py-16"
    >
      <div className="max-w-4xl border-y border-ink py-7 sm:py-10">
        <Construction className="size-10 text-muted" aria-hidden="true" />
        <h1 className="mt-6 font-display text-3xl font-bold tracking-[-0.045em] uppercase sm:text-5xl">
          {title}
        </h1>
        <p className="mt-4 max-w-xl leading-7 text-muted">{body}</p>
        <Link
          href={`/${locale}`}
          className="mt-8 inline-flex min-h-11 items-center gap-2 border border-ink px-4 text-sm font-bold hover:bg-neon"
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          {back}
        </Link>
      </div>
    </main>
  );
}
