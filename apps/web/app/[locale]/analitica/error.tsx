"use client";

export default function AnalysisError({ reset }: { reset: () => void }) {
  return (
    <main
      id="main-content"
      className="mx-auto max-w-[1440px] px-[clamp(1rem,5.55vw,5rem)] py-12"
    >
      <section className="border border-ink p-6" role="alert">
        <h1 className="font-display text-3xl font-bold uppercase">
          Analysis unavailable / Análisis no disponible
        </h1>
        <p className="mt-4 max-w-2xl text-sm leading-6 text-muted">
          Missing or offline resources are not replaced with zeros or sample
          conclusions. / Los recursos ausentes o sin conexión no se sustituyen
          por ceros ni conclusiones de muestra.
        </p>
        <button
          className="mt-6 min-h-11 border border-ink bg-ink px-4 font-mono text-xs font-bold uppercase text-paper hover:bg-neon hover:text-ink"
          onClick={reset}
          type="button"
        >
          Retry / Reintentar
        </button>
      </section>
    </main>
  );
}
