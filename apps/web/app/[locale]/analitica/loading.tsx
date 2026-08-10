"use client";

import { useParams } from "next/navigation";

import enMessages from "@/messages/en.json";
import esMessages from "@/messages/es.json";

export default function AnalysisLoading() {
  const params = useParams<{ locale?: string }>();
  const text =
    params.locale === "en" ? enMessages.analysis : esMessages.analysis;
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="mx-auto max-w-[1440px] animate-pulse px-[clamp(1rem,5.55vw,5rem)] py-8 sm:py-12"
      aria-busy="true"
      aria-label={text.loading}
      role="status"
    >
      <div className="h-12 border border-ink bg-line" />
      <div className="mt-8 h-40 border border-ink bg-line" />
      <div className="mt-4 h-72 border border-ink bg-line" />
      <p className="sr-only">{text.loading}</p>
    </main>
  );
}
