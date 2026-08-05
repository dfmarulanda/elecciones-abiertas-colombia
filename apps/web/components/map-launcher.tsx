"use client";

import { Map } from "lucide-react";
import React, { type ComponentType, useRef, useState } from "react";

import type { ResultMapProps } from "./result-map";

/**
 * Territory is secondary expert detail. Import its dialog only after an explicit
 * request so the result table remains the small, immediate first experience.
 */
export function MapLauncher({
  locale,
  rows,
}: Pick<ResultMapProps, "locale" | "rows">) {
  const [Dialog, setDialog] = useState<ComponentType<ResultMapProps> | null>(
    null,
  );
  const triggerRef = useRef<HTMLButtonElement>(null);

  const open = () => {
    void import("./result-map")
      .then(({ ResultMap }) => setDialog(() => ResultMap))
      .catch(() => triggerRef.current?.focus());
  };

  return Dialog ? (
    <Dialog
      locale={locale}
      rows={rows}
      hideTrigger
      initiallyOpen
      onDismiss={() => {
        setDialog(null);
        window.requestAnimationFrame(() => triggerRef.current?.focus());
      }}
    />
  ) : (
    <button
      className="inline-flex min-h-11 items-center gap-2 border border-ink px-4 text-sm font-bold hover:bg-neon"
      onClick={open}
      ref={triggerRef}
    >
      <Map className="size-4" aria-hidden="true" />
      {locale === "es" ? "Abrir mapa" : "Open map"}
    </button>
  );
}
