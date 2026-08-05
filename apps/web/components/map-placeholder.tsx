"use client";

import { MapPinned } from "lucide-react";

export function MapPlaceholder({ label }: { label: string }) {
  return (
    <div
      className="grid min-h-72 place-items-center border border-ink bg-paper p-6 text-center"
      aria-label={label}
      role="img"
    >
      <div className="max-w-sm">
        <MapPinned className="mx-auto size-9 text-ink" aria-hidden="true" />
        <p className="mt-3 text-sm font-semibold">{label}</p>
        <p className="mt-2 text-sm leading-6 text-muted">
          No se muestran límites ni ubicaciones hasta que esta versión incluya
          datos departamentales con una equivalencia revisada.
        </p>
      </div>
    </div>
  );
}
