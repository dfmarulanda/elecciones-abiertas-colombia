"use client";

import { useParams } from "next/navigation";

import enMessages from "@/messages/en.json";
import esMessages from "@/messages/es.json";

export default function AnalysisError({ reset }: { reset: () => void }) {
  const params = useParams<{ locale?: string }>();
  const text =
    params.locale === "en" ? enMessages.analysis : esMessages.analysis;
  return (
    <main
      id="main-content"
      className="mx-auto max-w-[1440px] px-[clamp(1rem,5.55vw,5rem)] py-12"
    >
      <section className="border border-ink p-6" role="alert">
        <h1 className="font-display text-3xl font-bold uppercase">
          {text.errorTitle}
        </h1>
        <p className="mt-4 max-w-2xl text-sm leading-6 text-muted">
          {text.errorBody}
        </p>
        <button
          className="mt-6 min-h-11 border border-ink bg-ink px-4 font-mono text-xs font-bold uppercase text-paper hover:bg-neon hover:text-ink"
          onClick={reset}
          type="button"
        >
          {text.retry}
        </button>
      </section>
    </main>
  );
}
