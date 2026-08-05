"use client";

import { useEffect } from "react";
import { reportClientError } from "@/lib/client-error-reporting";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    reportClientError("react_global_error", error);
  }, [error]);

  return (
    <html lang="es">
      <body className="bg-paper text-ink">
        <main className="mx-auto max-w-[1440px] px-[clamp(1rem,5.55vw,5rem)] py-20">
          <p className="font-mono text-xs font-bold tracking-[.14em] text-muted uppercase">
            Error de aplicación · Application error
          </p>
          <h1 className="mt-3 max-w-3xl border-y border-ink py-6 font-display text-3xl font-bold tracking-[-0.045em] uppercase sm:text-5xl">
            No pudimos mostrar esta página
          </h1>
          <p className="mt-5 max-w-xl leading-7 text-muted">
            We could not display this page. If monitoring is configured, its
            report excludes visitor-identifying data.
          </p>
          <button
            className="mt-7 min-h-11 border border-ink bg-ink px-5 font-bold text-paper hover:bg-neon hover:text-ink"
            onClick={reset}
          >
            Intentar de nuevo · Try again
          </button>
        </main>
      </body>
    </html>
  );
}
