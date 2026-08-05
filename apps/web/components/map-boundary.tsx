"use client";

import dynamic from "next/dynamic";

const MapPlaceholder = dynamic(
  () => import("./map-placeholder").then((module) => module.MapPlaceholder),
  {
    ssr: false,
    loading: () => (
      <div
        className="min-h-72 animate-pulse border border-ink bg-paper"
        aria-hidden="true"
      />
    ),
  },
);

export function MapBoundary({ label }: { label: string }) {
  return <MapPlaceholder label={label} />;
}
