"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { geoGraticule, geoMercator, geoPath } from "d3-geo";
import { feature } from "topojson-client";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import type { GeometryCollection, Topology } from "topojson-specification";
import {
  TERRITORIES,
  UNCOVERED_DEPARTMENTS_COUNT,
  territoryTotals,
} from "@/lib/dc-fixture";
import { WORLD_ATLAS_BOUNDARY } from "@/lib/world-atlas-boundary";

type Locale = "es" | "en";

/**
 * Every string CoverageMap needs, already resolved by the server component
 * that renders it. `next-intl`'s `t` is a server-only function and cannot
 * cross into a Client Component as a prop — React rejects functions there —
 * so `TerritoriesSection` resolves the strings once and passes plain data.
 */
export type CoverageMapLabels = {
  mapTitle: string;
  legendReporting: string;
  legendNotCollected: string;
  legendDepartments: string;
  note: string;
  error: string;
  tooltipOf: string;
  tooltipPrecount: string;
  noscript: string;
  mesasUnit: string;
  votesUnit: string;
  territoryNames: Record<(typeof TERRITORIES)[number]["key"], string>;
};

/**
 * The coverage map, ported from the design's `mapa-cobertura.html` — same
 * Mercator fit on the Colombia land feature, same background/graticule/land
 * layers and colours, same glow-marker treatment for the two reporting
 * territories, same legend and geometry note. Reproduces the D3 draw exactly;
 * see the module doc below for the two places the Next.js/CSP environment
 * forced a different mechanism rather than a different result.
 *
 * Adaptations from the source (both forced by this environment, not stylistic):
 *  1. `d3.json(...)` fetched `world-atlas` off jsdelivr; the strict CSP here
 *     has no CDN in connect-src, so the identical file is vendored at
 *     `/public/maps/countries-110m.json` (see `WORLD_ATLAS_BOUNDARY` for the
 *     hash) and fetched same-origin instead.
 *  2. The source drew through `d3-selection` (`svg.append(...).join(...)`),
 *     imperatively mutating a DOM the framework doesn't own. Here the SVG is
 *     plain JSX and only the geometry math — `d3-geo`'s projection, path and
 *     graticule — is the same D3 code as the source; React does the
 *     reconciliation instead of `d3-selection`. The pixels are unchanged.
 *  3. The source redrew on `window.resize`, sized to a full-viewport iframe.
 *     Embedded directly in a grid column here, a `ResizeObserver` on the
 *     wrapper replaces the window listener so the map also redraws when its
 *     own column resizes, not only the window.
 *  4. Markers gained keyboard focus handling (`onFocus`/`onBlur` alongside
 *     `onMouseMove`/`onMouseLeave`) so the tooltip is reachable without a
 *     mouse — the source only wired `mousemove`/`mouseleave`. The always-
 *     rendered table in `TerritoriesSection` is the actual accessible
 *     equivalent; this is a small keyboard-parity addition on top of it.
 */

const INK = "#F4F1EA";
const ST100 = "#211E1E";
const ST200 = "#2E2A27";
const ST300 = "#3A3531";
const PAPER = "#151312";
const GLOW = "#C4FF00";

type CountriesTopology = Topology<{
  countries: GeometryCollection;
  land: GeometryCollection;
}>;

type MarkerDatum = {
  key: (typeof TERRITORIES)[number]["key"];
  x: number;
  y: number;
  name: string;
  mesas: number;
  horizonte: number;
  rio: number;
  total: number;
};

type TooltipState = {
  key: string;
  left: number;
  top: number;
};

export function CoverageMap({
  locale,
  labels,
  fullCoverage = false,
}: {
  locale: Locale;
  labels: CoverageMapLabels;
  /** Real preconteo: nationally complete, so the illustrative two-territory
   * markers are suppressed and Colombia renders as fully covered. */
  fullCoverage?: boolean;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [land, setLand] = useState<FeatureCollection<Geometry> | null>(null);
  const [colombia, setColombia] = useState<Feature<Geometry> | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const gradientId = useId();
  const nf = useMemo(() => new Intl.NumberFormat(locale === "es" ? "es-CO" : "en-US"), [locale]);

  useEffect(() => {
    let alive = true;
    fetch(WORLD_ATLAS_BOUNDARY.vendoredPath)
      .then((res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.json() as Promise<CountriesTopology>;
      })
      .then((topo) => {
        if (!alive) return;
        const collection = feature(topo, topo.objects.countries) as FeatureCollection<Geometry>;
        const co =
          collection.features.find((f) => f.properties?.name === "Colombia") ??
          null;
        setLand(collection);
        setColombia(co);
        setStatus(co ? "ready" : "error");
      })
      .catch(() => {
        if (alive) setStatus("error");
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { w, h } = size;
  const ready = status === "ready" && !!colombia && !!land && w > 0 && h > 0;

  const geometry = useMemo(() => {
    if (!ready || !colombia || !land) return null;
    const projection = geoMercator().fitExtent(
      [
        [46, 40],
        [w - 46, h - 56],
      ],
      colombia,
    );
    const path = geoPath(projection);
    const colombiaD = path(colombia) ?? "";
    const graticuleD = path(geoGraticule().step([5, 5])()) ?? "";
    const otherLand = land.features
      .filter((f) => f.properties?.name !== "Colombia")
      .map((f, i) => ({ key: String(f.id ?? i), d: path(f) ?? "" }))
      .filter((f) => f.d);
    const markers: MarkerDatum[] = fullCoverage
      ? []
      : TERRITORIES.map((territory) => {
          const point = projection([territory.lon, territory.lat]);
          if (!point) return null;
          const totals = territoryTotals(territory.key);
          return {
            key: territory.key,
            x: point[0],
            y: point[1],
            name: labels.territoryNames[territory.key],
            mesas: totals.mesas,
            horizonte: totals.horizonte,
            rio: totals.rio,
            total: totals.total,
          };
        }).filter((m): m is MarkerDatum => m !== null);
    return { colombiaD, graticuleD, otherLand, markers };
  }, [ready, colombia, land, w, h, labels.territoryNames, fullCoverage]);

  const showTooltip = (
    marker: MarkerDatum,
    clientX: number,
    clientY: number,
  ) => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTooltip({
      key: marker.key,
      left: Math.min(clientX - rect.left + 14, rect.width - 236),
      top: Math.max(clientY - rect.top - 10, 8),
    });
  };

  const activeMarker = geometry?.markers.find((m) => m.key === tooltip?.key);
  const mesasUnit = labels.mesasUnit;
  const votesUnit = labels.votesUnit;

  return (
    <div
      ref={wrapRef}
      className="relative h-full w-full overflow-hidden"
      style={{ background: PAPER, color: INK }}
    >
      <svg
        role="img"
        aria-label={labels.mapTitle}
        viewBox={`0 0 ${w || 1} ${h || 1}`}
        className="block h-full w-full"
      >
        <defs>
          <radialGradient id={gradientId}>
            <stop offset="0%" stopColor={GLOW} stopOpacity={0.55} />
            <stop offset="100%" stopColor={GLOW} stopOpacity={0} />
          </radialGradient>
        </defs>
        <rect width={w || 0} height={h || 0} fill={PAPER} />
        {geometry ? (
          <>
            <path
              d={geometry.graticuleD}
              fill="none"
              stroke={ST200}
              strokeWidth={0.6}
              strokeOpacity={0.8}
            />
            {geometry.otherLand.map((f) => (
              <path key={f.key} d={f.d} fill={ST100} stroke={PAPER} strokeWidth={1} />
            ))}
            <path
              d={geometry.colombiaD}
              fill={fullCoverage ? GLOW : ST300}
              fillOpacity={fullCoverage ? 0.35 : 1}
              stroke={INK}
              strokeWidth={1.1}
              strokeLinejoin="round"
            />
            {geometry.markers.map((marker) => (
              <g
                key={marker.key}
                transform={`translate(${marker.x},${marker.y})`}
              >
                <circle r={46} fill={`url(#${gradientId})`} />
                <circle
                  r={13}
                  fill="none"
                  stroke={INK}
                  strokeWidth={1}
                  strokeOpacity={0.35}
                />
                <circle
                  r={6.5}
                  fill={tooltip?.key === marker.key ? GLOW : INK}
                  stroke={PAPER}
                  strokeWidth={2}
                  className="motion-safe:transition-colors motion-safe:duration-150"
                />
                {/* Focusable hit target: keyboard users get the same tooltip
                    hover gives mouse users (adaptation 4 above). */}
                <circle
                  r={22}
                  fill="transparent"
                  tabIndex={0}
                  role="button"
                  aria-label={`${marker.name} · ${marker.mesas} ${mesasUnit} · Horizonte ${nf.format(marker.horizonte)} · Río ${nf.format(marker.rio)}`}
                  className="cursor-default outline-none"
                  onMouseMove={(e) => showTooltip(marker, e.clientX, e.clientY)}
                  onMouseLeave={() => setTooltip(null)}
                  onFocus={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    showTooltip(marker, rect.left + rect.width / 2, rect.top);
                  }}
                  onBlur={() => setTooltip(null)}
                />
                <text
                  x={20}
                  y={4}
                  fill={INK}
                  fontSize={12}
                  fontWeight={700}
                  paintOrder="stroke"
                  stroke={PAPER}
                  strokeWidth={4}
                  strokeLinejoin="round"
                  className="ec-mark pointer-events-none select-none"
                >
                  {marker.name}
                </text>
                <text
                  x={20}
                  y={20}
                  fill="#928979"
                  fontSize={12}
                  fontWeight={400}
                  paintOrder="stroke"
                  stroke={PAPER}
                  strokeWidth={4}
                  strokeLinejoin="round"
                  className="ec-mono pointer-events-none select-none"
                >
                  {marker.mesas} {mesasUnit}
                </text>
              </g>
            ))}
          </>
        ) : null}
      </svg>

      {status === "error" ? (
        <p
          role="status"
          className="absolute inset-x-4 top-4 m-0 text-[11px] leading-relaxed text-[color:var(--on-dark-3)]"
        >
          {labels.error}
        </p>
      ) : null}

      {activeMarker && tooltip ? (
        <div
          role="tooltip"
          className="pointer-events-none absolute max-w-[220px] border px-3 py-2.5 text-[12px] leading-relaxed"
          style={{
            left: tooltip.left,
            top: tooltip.top,
            borderColor: "rgba(244,241,234,.28)",
            background: "#211E1E",
            boxShadow: "0 8px 24px rgba(0,0,0,.5)",
          }}
        >
          <p className="m-0 font-bold">{activeMarker.name}</p>
          <p className="ec-mono m-0 mt-1">
            {activeMarker.mesas} {mesasUnit}
          </p>
          <p className="ec-mono m-0 mt-1">
            Horizonte {nf.format(activeMarker.horizonte)} · Río{" "}
            {nf.format(activeMarker.rio)}
          </p>
          <p className="m-0 mt-1 text-[color:var(--on-dark-3)]">
            {labels.tooltipOf}{" "}
            <span className="ec-mono">{nf.format(activeMarker.total)}</span>{" "}
            {votesUnit} · {labels.tooltipPrecount}
          </p>
        </div>
      ) : null}

      <div
        className="absolute bottom-4 left-4 flex flex-col gap-2 border px-3.5 py-3 text-[12px] leading-tight"
        style={{
          borderColor: "rgba(244,241,234,.24)",
          background: "rgba(21,19,18,.92)",
        }}
      >
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="inline-block size-3 shrink-0 rounded-full"
            style={{ background: INK }}
          />
          <span>
            {labels.legendReporting}{" "}
            <b className="ec-mono">{TERRITORIES.length}</b>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="inline-block size-3 shrink-0 rounded-full"
            style={{ background: ST300 }}
          />
          <span>
            {labels.legendNotCollected}{" "}
            <b className="ec-mono">{UNCOVERED_DEPARTMENTS_COUNT}</b>{" "}
            {labels.legendDepartments}
          </span>
        </div>
      </div>

      <p
        className="absolute bottom-4 right-4 m-0 max-w-[260px] text-right text-[11px] leading-relaxed"
        style={{ color: "#928979" }}
      >
        {labels.note}
      </p>

      <noscript>
        <p className="absolute inset-4 m-0 text-[13px] leading-relaxed" style={{ color: INK }}>
          {labels.noscript}
        </p>
      </noscript>
    </div>
  );
}
