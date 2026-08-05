"use client";

import maplibregl from "maplibre-gl";
import {
  AlertCircle,
  CheckCircle2,
  LoaderCircle,
  MapPinned,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  DANE_DEPARTMENT_BOUNDARY,
  type ReviewedDepartment,
} from "@/lib/department-map";

type Props = {
  locale: "es" | "en";
  rows: ReviewedDepartment[];
  selectedCode: string | null;
};

type Geometry = {
  type: "Polygon" | "MultiPolygon";
  coordinates: unknown;
};

type BoundaryFeature = {
  properties?: Record<string, unknown>;
  geometry?: Geometry;
};

type BoundaryCollection = {
  type: "FeatureCollection";
  features: BoundaryFeature[];
};

type Position = [number, number];
type Ring = Position[];

type MapState = "loading" | "ready" | "unavailable";

const neutralColor = "#F2F2F2";
const colors = [neutralColor, "#D4D4D4", "#9B9B9B", "#5A8A3A"] as const;
const activeColor = "#C4FF00";
const inkColor = "#0A0A0A";

function departmentFill(
  rows: ReviewedDepartment[],
  selectedCode?: string | null,
): maplibregl.ExpressionSpecification {
  const base = [
    "match",
    ["get", "dpto_ccdgo"],
    ...rows.flatMap((row, index) => [
      row.daneCode,
      colors[index % colors.length] ?? neutralColor,
    ]),
    neutralColor,
  ] as unknown as maplibregl.ExpressionSpecification;
  return selectedCode
    ? ([
        "case",
        ["==", ["get", "dpto_ccdgo"], selectedCode],
        activeColor,
        base,
      ] as unknown as maplibregl.ExpressionSpecification)
    : base;
}

function boundaryRings(feature: BoundaryFeature): Ring[] {
  const coordinates = feature.geometry?.coordinates;
  if (!Array.isArray(coordinates)) return [];
  if (feature.geometry?.type === "Polygon") return coordinates as Ring[];
  if (feature.geometry?.type === "MultiPolygon") {
    return (coordinates as Ring[][]).flat();
  }
  return [];
}

function BoundaryFallback({
  features,
  rows,
  selectedCode,
}: {
  features: BoundaryFeature[];
  rows: ReviewedDepartment[];
  selectedCode: string | null;
}) {
  const points = features.flatMap(boundaryRings).flat();
  if (!points.length) return null;
  const longitudes = points.map(([longitude]) => longitude);
  const latitudes = points.map(([, latitude]) => latitude);
  const minimumLongitude = Math.min(...longitudes);
  const maximumLongitude = Math.max(...longitudes);
  const minimumLatitude = Math.min(...latitudes);
  const maximumLatitude = Math.max(...latitudes);
  const horizontal = Math.max(maximumLongitude - minimumLongitude, 0.01);
  const vertical = Math.max(maximumLatitude - minimumLatitude, 0.01);
  const padding = 36;
  const project = ([longitude, latitude]: Position): Position => [
    padding +
      ((longitude - minimumLongitude) / horizontal) * (1000 - padding * 2),
    padding + ((maximumLatitude - latitude) / vertical) * (700 - padding * 2),
  ];
  const colorsByCode = Object.fromEntries(
    rows.map((row, index) => [
      row.daneCode,
      colors[index % colors.length] ?? neutralColor,
    ]),
  );

  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 size-full"
      data-testid="department-map-svg-fallback"
      preserveAspectRatio="xMidYMid meet"
      viewBox="0 0 1000 700"
    >
      {features.flatMap((feature) => {
        const code = String(feature.properties?.dpto_ccdgo ?? "");
        const selected = code === selectedCode;
        const fill = selected
          ? activeColor
          : (colorsByCode[code] ?? neutralColor);
        return boundaryRings(feature).map((ring, index) => (
          <path
            data-selected={selected ? "true" : "false"}
            d={
              ring
                .map((point, pointIndex) => {
                  const [x, y] = project(point);
                  return `${pointIndex ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`;
                })
                .join(" ") + " Z"
            }
            fill={fill}
            fillOpacity="0.92"
            key={`${code}-${index}`}
            stroke={inkColor}
            strokeDasharray={selected ? "12 7" : undefined}
            strokeWidth={selected ? "8" : "3"}
          />
        ));
      })}
    </svg>
  );
}

export function DepartmentMap({ locale, rows, selectedCode }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [state, setState] = useState<MapState>("loading");
  const [renderedFeatures, setRenderedFeatures] = useState(0);
  const [fallbackFeatures, setFallbackFeatures] = useState<BoundaryFeature[]>(
    [],
  );
  const es = locale === "es";

  useEffect(() => {
    const element = container.current;
    if (!element || !rows.length) {
      setState("unavailable");
      return;
    }
    const controller = new AbortController();
    let map: maplibregl.Map | null = null;

    const load = async () => {
      try {
        const response = await fetch(
          "/maps/dane-departments-2025-simplified.geojson",
          {
            signal: controller.signal,
          },
        );
        if (!response.ok) throw new Error("Boundary asset unavailable");
        const boundary = (await response.json()) as BoundaryCollection;
        if (controller.signal.aborted) return;
        const allowed = new Set(rows.map((row) => row.daneCode));
        const data = {
          ...boundary,
          features: boundary.features.filter((feature) =>
            allowed.has(String(feature.properties?.dpto_ccdgo ?? "")),
          ),
        } as BoundaryCollection;
        if (!data.features.length) {
          setState("unavailable");
          return;
        }
        setFallbackFeatures(data.features);

        map = new maplibregl.Map({
          container: element,
          attributionControl: false,
          interactive: false,
          keyboard: false,
          canvasContextAttributes: { preserveDrawingBuffer: true },
          dragRotate: false,
          pitchWithRotate: false,
          style: {
            version: 8,
            sources: {},
            layers: [
              {
                id: "paper",
                type: "background",
                paint: { "background-color": "#FFFFFF" },
              },
            ],
          },
        });
        mapRef.current = map;

        const ready = () => {
          if (!map || controller.signal.aborted) return;
          map.getCanvas().tabIndex = -1;
          map.getCanvas().setAttribute("aria-hidden", "true");
          map.getCanvas().style.pointerEvents = "none";
          map.addSource("departments", {
            type: "geojson",
            data: data as never,
          });
          map.addLayer({
            id: "departments-fill",
            type: "fill",
            source: "departments",
            paint: {
              "fill-color": departmentFill(rows),
              "fill-opacity": 0.92,
            },
          });
          map.addLayer({
            id: "departments-line",
            type: "line",
            source: "departments",
            paint: { "line-color": inkColor, "line-width": 1.25 },
          });
          const bounds = data.features.reduce((next, feature) => {
            const visit = (value: unknown) => {
              if (!Array.isArray(value)) return;
              if (
                value.length >= 2 &&
                typeof value[0] === "number" &&
                typeof value[1] === "number"
              ) {
                next.extend([value[0], value[1]]);
                return;
              }
              value.forEach(visit);
            };
            visit(feature.geometry?.coordinates);
            return next;
          }, new maplibregl.LngLatBounds());
          if (!bounds.isEmpty())
            map.fitBounds(bounds, { padding: 24, duration: 0 });
          window.requestAnimationFrame(() => {
            if (!map || controller.signal.aborted) return;
            map.resize();
            map.once("idle", () => {
              const visible = map?.queryRenderedFeatures({
                layers: ["departments-fill"],
              }).length;
              if (!visible) {
                setState("unavailable");
                return;
              }
              setRenderedFeatures(visible);
              setState("ready");
            });
            map.triggerRepaint();
          });
        };
        map.once("load", ready);
        map.once("error", () => setState("unavailable"));
      } catch {
        if (!controller.signal.aborted) setState("unavailable");
      }
    };
    void load();

    return () => {
      controller.abort();
      map?.remove();
      mapRef.current = null;
    };
  }, [rows]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer("departments-line")) return;
    if (map.getLayer("departments-fill")) {
      map.setPaintProperty(
        "departments-fill",
        "fill-color",
        departmentFill(rows, selectedCode),
      );
    }
    map.setPaintProperty("departments-line", "line-width", [
      "case",
      ["==", ["get", "dpto_ccdgo"], selectedCode],
      3,
      1.25,
    ]);
  }, [rows, selectedCode]);

  return (
    <div className="relative min-h-72 overflow-hidden border border-ink bg-paper">
      <div
        ref={container}
        className="absolute inset-0"
        aria-hidden="true"
        data-testid="department-map-canvas"
        data-rendered-features={renderedFeatures}
      />
      <BoundaryFallback
        features={fallbackFeatures}
        rows={rows}
        selectedCode={selectedCode}
      />
      {state === "loading" ? (
        <div className="absolute inset-0 grid place-items-center bg-paper/95 text-sm font-semibold">
          <span className="inline-flex items-center gap-2">
            <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
            {es
              ? "Cargando límites revisados…"
              : "Loading reviewed boundaries…"}
          </span>
        </div>
      ) : null}
      {state === "unavailable" ? (
        <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm leading-6 text-muted">
          <span>
            <AlertCircle
              className="mx-auto mb-2 size-5 text-ink"
              aria-hidden="true"
            />
            {es
              ? "No se pudo mostrar el límite revisado. La tabla equivalente sigue disponible."
              : "The reviewed boundary could not be shown. The equivalent table remains available."}
          </span>
        </div>
      ) : null}
      {state === "ready" ? (
        <div className="pointer-events-none absolute bottom-3 left-3 max-w-xs border border-ink bg-paper/95 px-3 py-2 text-xs leading-5">
          <span className="inline-flex items-center gap-1 font-bold">
            <CheckCircle2 className="size-3.5 text-ink" aria-hidden="true" />
            {es
              ? "Derivado local revisado de límites oficiales"
              : "Reviewed local derivative of official boundaries"}
          </span>
          <span className="block text-muted">
            {es
              ? "Seleccione un departamento en la tabla para resaltarlo aquí."
              : "Select a department in the table to highlight it here."}
          </span>
        </div>
      ) : null}
      <div className="sr-only" aria-live="polite">
        {selectedCode
          ? rows.find((row) => row.daneCode === selectedCode)?.daneName
          : es
            ? "Ningún departamento seleccionado"
            : "No department selected"}
      </div>
      <div className="sr-only">
        <MapPinned aria-hidden="true" />
        {DANE_DEPARTMENT_BOUNDARY.attribution}
      </div>
    </div>
  );
}
