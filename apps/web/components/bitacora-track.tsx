"use client";

import React, { useEffect, useRef, useState } from "react";
import { Gutter } from "@/components/page-primitives";

/** Flat-top hexagon: the same glyph the header wordmark and the process
 * section's step nodes use, reused here for the log's phase-stop markers. */
const HEX_CLIP = "polygon(0 50%, 25% 0, 75% 0, 100% 50%, 75% 100%, 25% 100%)";

export type BitacoraStop = {
  key: string;
  when: string;
  title: string;
  body: string;
};

/**
 * #bitacora's `bitacora-track` / `bit-stage`: a horizontal timeline of phase
 * stops, reproduced from the design's scroll-linked scrollytelling stage.
 *
 * Fidelity note: the source design pins this stage with `position: sticky`
 * and drives an inner `translateX` off the PAGE's vertical scroll position --
 * a full-viewport scroll-jack. That mechanic fights three of this project's
 * own constraints at once: prefers-reduced-motion (the translateX has no
 * reduced-motion fallback in the source), keyboard operability (a
 * scroll-jacked track has no keyboard equivalent for "scroll the stage"),
 * and content that must stay in the DOM for assistive tech (the source fades
 * stops to opacity 0 until the page scroll reaches them). This reproduction
 * keeps the HORIZONTAL TRACK layout -- the stage, the phase stops staged
 * along a line with hex nodes, the live "current stop" readout, the trailing
 * progress bar -- but drives it off the track's OWN horizontal scroll
 * instead of the page's vertical scroll: `overflow-x: auto` with scroll-snap,
 * exposed as a `role="region"` with `tabIndex={0}` (the WAI-ARIA APG
 * "scrollable region" pattern, which browsers already wire to the arrow
 * keys), so it works with a mouse, a trackpad, touch, or a keyboard, and
 * every stop's text stays in the accessibility tree at all times instead of
 * being revealed by motion.
 */
export function BitacoraTrack({
  stops,
  regionLabel,
  hintLabel,
  milestoneWord,
  ofWord,
}: {
  stops: BitacoraStop[];
  regionLabel: string;
  hintLabel: string;
  milestoneWord: string;
  ofWord: string;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const stopRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [active, setActive] = useState(0);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const updateProgress = () => {
      const max = el.scrollWidth - el.clientWidth;
      setProgress(max > 0 ? Math.min(1, Math.max(0, el.scrollLeft / max)) : 0);
    };
    updateProgress();
    el.addEventListener("scroll", updateProgress, { passive: true });
    window.addEventListener("resize", updateProgress);
    return () => {
      el.removeEventListener("scroll", updateProgress);
      window.removeEventListener("resize", updateProgress);
    };
  }, []);

  useEffect(() => {
    const root = trackRef.current;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        let bestIndex: number | null = null;
        let bestRatio = 0;
        for (const entry of entries) {
          const raw = (entry.target as HTMLElement).dataset.index;
          if (raw === undefined) continue;
          if (entry.intersectionRatio > bestRatio) {
            bestRatio = entry.intersectionRatio;
            bestIndex = Number(raw);
          }
        }
        if (bestIndex !== null) setActive(bestIndex);
      },
      { root, rootMargin: "0px -35% 0px -35%", threshold: [0.2, 0.5, 0.8, 1] },
    );
    stopRefs.current.forEach((node) => node && observer.observe(node));
    return () => observer.disconnect();
  }, [stops.length]);

  const current = stops[active] ?? stops[0];

  return (
    <div className="ec-field-dark mt-9">
      <Gutter className="flex flex-wrap items-baseline justify-between gap-4 py-5">
        <div className="min-w-0">
          <p className="ec-mark m-0 truncate text-[11px] text-neon">
            {current?.title}
          </p>
          <p className="ec-mono mt-1.5 text-[12px] text-on-dark-3">
            {current?.when}
          </p>
        </div>
        <p className="ec-mono m-0 shrink-0 text-[12px] text-on-dark-3">
          {milestoneWord} {active + 1} {ofWord} {stops.length}
        </p>
      </Gutter>

      <p id="bitacora-track-hint" className="sr-only">
        {hintLabel}
      </p>
      <div
        ref={trackRef}
        role="region"
        aria-label={regionLabel}
        aria-describedby="bitacora-track-hint"
        tabIndex={0}
        className="snap-x snap-mandatory overflow-x-auto scroll-smooth px-gutter pt-3 pb-9 [scrollbar-width:thin] motion-reduce:scroll-auto"
      >
        <div className="inline-flex items-stretch">
          {stops.map((stop, i) => (
            <div
              key={stop.key}
              ref={(node) => {
                stopRefs.current[i] = node;
              }}
              data-index={i}
              className="relative w-[260px] shrink-0 snap-center"
            >
              <div className="flex h-[62px] flex-col items-center justify-end px-6 text-center">
                <p className="ec-mark m-0 text-[11px] text-neon">
                  {String(i + 1).padStart(2, "0")}
                </p>
                <p className="ec-mono mt-1.5 truncate text-[11px] text-on-dark-3">
                  {stop.when}
                </p>
              </div>
              <div
                aria-hidden="true"
                className="mx-auto h-3 w-px bg-[color:var(--rule-dark-soft)]"
              />
              <div className="relative flex h-[17px] items-center justify-center">
                <span
                  aria-hidden="true"
                  className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-[color:var(--rule-dark-soft)]"
                />
                <span
                  aria-hidden="true"
                  className="relative z-10 block h-[15px] w-[17px] bg-neon"
                  style={{ clipPath: HEX_CLIP }}
                />
              </div>
              <div className="px-6 pt-4 text-center">
                <p className="m-0 text-[15px] font-semibold tracking-[-.01em] text-on-dark">
                  {stop.title}
                </p>
                <p className="mt-2 text-[13px] leading-relaxed text-on-dark-2">
                  {stop.body}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <Gutter className="pb-7">
        <div className="h-0.5 bg-[color:var(--rule-dark-faint)]">
          <div
            className="h-full bg-neon transition-[width] duration-300 ease-out motion-reduce:transition-none"
            style={{ width: `${(progress * 100).toFixed(1)}%` }}
          />
        </div>
      </Gutter>
    </div>
  );
}
