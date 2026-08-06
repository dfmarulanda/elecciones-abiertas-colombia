"use client";

import React, { useEffect, useRef, useState } from "react";

/* #bitacora's `bitacora-track` / `bit-stage`, transcribed verbatim from the
 * Rediseño v2 design source (dc-data.js). This is NOT a flat timeline: the
 * stops sit on a sine wave (`y = 300 + sin(i*0.78+0.4)*74`), a neon polyline
 * draws progressively as the stage is scrolled, and the whole track is a
 * sticky scroll-jacked stage whose inner strip translates on the page's
 * vertical scroll -- the exact mechanic and geometry the design ships.
 *
 * Accessibility layer added on top of the faithful visual (not a substitute
 * for it): every stop's text stays in the DOM at all times, so opacity fades
 * are purely visual and assistive tech always reads the full log; and under
 * prefers-reduced-motion the fades/scales/dash animation are disabled and all
 * stops are revealed, while the scroll-linked position (direct manipulation,
 * not autonomous motion) is preserved. */

const HEX_CLIP = "polygon(0 50%, 25% 0, 75% 0, 100% 50%, 75% 100%, 25% 100%)";

// dc-data.js: MAP_X0=180, MAP_DX=234, MAP_W=3010, MAP_H=560
const MAP_X0 = 180;
const MAP_DX = 234;
const MAP_W = 3010;
const MAP_H = 560;

export type BitacoraStop = {
  key: string;
  phase: string;
  phaseN: string;
  when: string;
  title: string;
  body: string;
  first: boolean;
};

type Geo = { x: number; y: number };

// y = 300 + round(sin(i*0.78 + 0.4) * 74) -- the curve, byte-for-byte.
const geometry = (count: number): Geo[] =>
  Array.from({ length: count }, (_, i) => ({
    x: MAP_X0 + i * MAP_DX,
    y: 300 + Math.round(Math.sin(i * 0.78 + 0.4) * 74),
  }));

const pathOf = (geo: Geo[]) => geo.map((g) => `${g.x},${g.y}`).join(" ");

const lengthOf = (geo: Geo[]) => {
  let total = 0;
  for (let i = 1; i < geo.length; i += 1) {
    total += Math.hypot(geo[i]!.x - geo[i - 1]!.x, geo[i]!.y - geo[i - 1]!.y);
  }
  return Math.round(total);
};

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
  const stageRef = useRef<HTMLDivElement>(null);
  const [bitP, setBitP] = useState(0);
  const [stageW, setStageW] = useState(1200);
  // Starts `true` so the server-rendered markup and the first client render
  // agree (no `matchMedia` on the server); the real preference is read once
  // mounted, same as `reduced`'s own effect below.
  const [reduced, setReduced] = useState(true);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  // dc-data.js's own componentDidMount: a requestAnimationFrame loop, not a
  // scroll/resize listener, re-reading layout every frame and only committing
  // state when it moved past a small threshold. Only runs for the motion
  // path -- under reduced motion this component never mounts the scroll-jacked
  // stage at all (see the early return below), so there is nothing to drive.
  useEffect(() => {
    if (reduced) return;
    let alive = true;
    let frame = 0;
    const tick = () => {
      if (!alive) return;
      frame = requestAnimationFrame(tick);
      if (document.hidden) return;
      const stage = stageRef.current;
      const track = stage?.parentElement;
      if (!stage || !track) return;

      const nextStageW = stage.clientWidth;
      const rect = track.getBoundingClientRect();
      const span = track.offsetHeight - stage.clientHeight;
      // dc-data.js scroll model: the outer track is (100vh + 2000px) tall and
      // the stage is sticky at top:66px; bitP = (66 - rect.top) / scrollSpan.
      const nextBitP = span > 0 ? Math.min(1, Math.max(0, (66 - rect.top) / span)) : 0;

      setBitP((prev) => (Math.abs(prev - nextBitP) > 0.0012 ? nextBitP : prev));
      setStageW((prev) => (prev !== nextStageW ? nextStageW : prev));
    };
    frame = requestAnimationFrame(tick);
    return () => {
      alive = false;
      cancelAnimationFrame(frame);
    };
  }, [reduced]);

  const geo = geometry(stops.length);
  const mapPath = pathOf(geo);
  const mapLen = lengthOf(geo);

  // travel = max(0, MAP_W - stageW + 120); trackX = travel * bitP;
  // edge = trackX + stageW - 150; seen = # of stops whose x <= edge.
  const travel = Math.max(0, MAP_W - stageW + 120);
  const trackX = travel * bitP;
  const edge = trackX + stageW - 150;
  let seen = 0;
  for (let i = 0; i < geo.length; i += 1) if (geo[i]!.x <= edge) seen = i + 1;

  const mapDash = Math.round(mapLen * (1 - Math.min(1, seen / geo.length)));
  const current = stops[Math.min(stops.length - 1, Math.max(0, seen - 1))];

  // Scroll-jacking an entire page's vertical scroll to drive a horizontal
  // transform is exactly the "motion triggered by scrolling" pattern
  // prefers-reduced-motion exists to suppress (WCAG 2.3.3) -- and it forces
  // ~2000px of otherwise-empty scroll distance that a reduced-motion reader
  // has no reason to sit through. Rather than keep the same scroll-jacked DOM
  // and merely mute its transitions (which still scroll-jacks, just without
  // easing), reduced motion gets a genuinely different, static layout: an
  // ordinary horizontally-scrollable strip. `role="region"` + `tabIndex=0` is
  // the WAI-ARIA APG "scrollable region" pattern, which browsers already wire
  // to the arrow keys, so it works with a mouse, a trackpad, touch, or a
  // keyboard -- and every stop's text is visible at full opacity throughout,
  // never gated behind scroll position.
  if (reduced) {
    return (
      <BitacoraTrackStatic
        stops={stops}
        regionLabel={regionLabel}
        hintLabel={hintLabel}
        milestoneWord={milestoneWord}
        ofWord={ofWord}
      />
    );
  }

  return (
    <div className="relative mt-[34px] h-[calc(100vh+2000px)]">
      <p id="bitacora-track-hint" className="sr-only">
        {hintLabel}
      </p>
      <div
        ref={stageRef}
        role="region"
        aria-label={regionLabel}
        aria-describedby="bitacora-track-hint"
        className="sticky top-[66px] h-[calc(100vh-66px)] min-h-[min(600px,calc(100vh-66px))] overflow-hidden bg-[#151312] text-[#F4F1EA]"
      >
        {/* header: current phase + milestone counter */}
        <div className="absolute inset-x-0 top-0 z-[2] flex items-baseline justify-between gap-6 px-[46px] py-[26px]">
          <div>
            <p className="ec-mark m-0 text-[11px] text-[#C4FF00]">
              {current?.phase}
            </p>
            <p className="ec-mono mt-[7px] text-[12px] text-[#928979]">
              {current?.when}
            </p>
          </div>
          <p className="ec-mono m-0 text-[12px] text-[#928979]">
            {milestoneWord} {Math.min(Math.max(seen, 1), geo.length)} {ofWord}{" "}
            {geo.length}
          </p>
        </div>

        {/* the scrolling strip: grid background + translateX off page scroll */}
        <div
          className="absolute left-0 top-0 h-full will-change-transform"
          style={{
            width: `${MAP_W}px`,
            transform: `translateX(-${trackX.toFixed(1)}px)`,
            backgroundImage:
              "linear-gradient(rgba(244,241,234,.045) 1px,transparent 1px),linear-gradient(90deg,rgba(244,241,234,.045) 1px,transparent 1px)",
            backgroundSize: "60px 60px",
          }}
        >
          <div
            className="absolute left-0 top-1/2"
            style={{ width: `${MAP_W}px`, height: `${MAP_H}px`, marginTop: `-${MAP_H / 2}px` }}
          >
            <svg
              viewBox={`0 0 ${MAP_W} ${MAP_H}`}
              role="img"
              aria-label={regionLabel}
              className="absolute inset-0 h-full w-full"
            >
              <polyline
                points={mapPath}
                fill="none"
                stroke="rgba(244,241,234,.15)"
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              <polyline
                points={mapPath}
                fill="none"
                stroke="#C4FF00"
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                strokeDasharray={mapLen}
                strokeDashoffset={mapDash}
                style={{ transition: "stroke-dashoffset 520ms cubic-bezier(.2,.7,.1,1)" }}
              />
            </svg>

            {stops.map((stop, i) => {
              const g = geo[i]!;
              const on = i < seen;
              const above = g.y < 300;
              return (
                <div
                  key={stop.key}
                  className="absolute h-0"
                  style={{ left: `${g.x}px`, top: `${g.y}px`, width: 216, marginLeft: -108 }}
                >
                  {/* phase label + tick: only on the first stop of each phase */}
                  {stop.first ? (
                    <div
                      className="absolute left-1/2 w-[216px] -translate-x-1/2 text-center"
                      style={{
                        top: `-${g.y - 78}px`,
                        opacity: on ? 1 : 0,
                        transition: "opacity 520ms cubic-bezier(.2,.7,.1,1)",
                      }}
                    >
                      <p className="ec-mark m-0 whitespace-nowrap text-[11px] text-[#C4FF00]">
                        {stop.phase}
                      </p>
                      <p className="ec-mono mt-1.5 text-[11px] text-[#928979]">
                        {stop.phaseN} · {stop.when}
                      </p>
                      <div
                        className="mx-auto mt-3 w-px bg-[rgba(196,255,0,.34)]"
                        style={{ height: `${Math.max(26, g.y - 104)}px` }}
                      />
                    </div>
                  ) : null}

                  {/* the hexagon node, sitting on the wave */}
                  <div
                    className="absolute left-1/2 top-0 h-[17px] w-[19px]"
                    style={{
                      background: stop.first ? "#C4FF00" : "#F4F1EA",
                      clipPath: HEX_CLIP,
                      opacity: on ? 1 : 0,
                      transform: on
                        ? "translate(-50%,-50%) scale(1)"
                        : "translate(-50%,-50%) scale(.2)",
                      transition:
                        "opacity 420ms cubic-bezier(.2,.7,.1,1),transform 480ms cubic-bezier(.2,.7,.1,1)",
                    }}
                  />

                  {/* the card, above the node when the wave dips, below when it rises */}
                  <div
                    className="absolute inset-x-0"
                    style={{
                      ...(above ? { top: 28 } : { bottom: 28 }),
                      opacity: on ? 1 : 0,
                      transform: on ? "translateY(0) scale(1)" : "translateY(16px) scale(.97)",
                      transition:
                        "opacity 520ms cubic-bezier(.2,.7,.1,1),transform 560ms cubic-bezier(.2,.7,.1,1)",
                    }}
                  >
                    <p className="m-0 text-[16px] font-semibold leading-[1.3] tracking-[-.01em] text-[#F4F1EA]">
                      {stop.title}
                    </p>
                    <p className="mt-2 text-[13.5px] leading-[1.55] text-[#CFC8BC]">
                      {stop.body}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* trailing progress bar */}
        <div className="absolute inset-x-[46px] bottom-[26px] z-[2] h-0.5 bg-[rgba(244,241,234,.16)]">
          <div
            className="h-full bg-[#C4FF00]"
            style={{ width: `${(bitP * 100).toFixed(1)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * The `prefers-reduced-motion: reduce` path: the same 12 stops, grouped by
 * phase, laid out as an ordinary horizontally-scrollable strip instead of a
 * page-scroll-jacked stage. No `calc(100vh+2000px)` track, no transform tied
 * to page scroll position, no opacity gate on any stop's text -- everything
 * is visible and in normal document flow at all times. `role="region"` +
 * `tabIndex=0` is the WAI-ARIA APG "scrollable region" pattern, which
 * browsers already wire to the arrow keys, so it works with a mouse, a
 * trackpad, touch, or a keyboard.
 */
function BitacoraTrackStatic({
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
    <div className="mt-[34px] bg-[#151312] text-[#F4F1EA]">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-baseline justify-between gap-6 px-[46px] py-5">
        <div className="min-w-0">
          <p className="ec-mark m-0 truncate text-[11px] text-[#C4FF00]">
            {current?.phase}
          </p>
          <p className="ec-mono mt-1.5 text-[12px] text-[#928979]">
            {current?.phaseN} · {current?.when}
          </p>
        </div>
        <p className="ec-mono m-0 shrink-0 text-[12px] text-[#928979]">
          {milestoneWord} {active + 1} {ofWord} {stops.length}
        </p>
      </div>

      <p id="bitacora-track-hint" className="sr-only">
        {hintLabel}
      </p>
      <div
        ref={trackRef}
        role="region"
        aria-label={regionLabel}
        aria-describedby="bitacora-track-hint"
        tabIndex={0}
        className="snap-x snap-mandatory overflow-x-auto scroll-smooth px-[46px] pt-3 pb-9 [scrollbar-width:thin]"
      >
        <div className="inline-flex items-stretch">
          {stops.map((stop, i) => (
            <div
              key={stop.key}
              ref={(node) => {
                stopRefs.current[i] = node;
              }}
              data-index={i}
              className="relative w-[240px] shrink-0 snap-center px-4"
            >
              {stop.first ? (
                <p className="ec-mark m-0 mb-2 text-[11px] text-[#C4FF00]">
                  {stop.phaseN} · {stop.phase}
                </p>
              ) : null}
              <p className="ec-mono m-0 text-[11px] text-[#928979]">{stop.when}</p>
              <div
                aria-hidden="true"
                className="relative my-3 flex h-[17px] items-center"
              >
                <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-[rgba(244,241,234,.24)]" />
                <span
                  className="relative z-10 block h-[15px] w-[17px] bg-[#F4F1EA]"
                  style={{ clipPath: HEX_CLIP }}
                />
              </div>
              <p className="m-0 text-[15px] font-semibold leading-snug tracking-[-.01em] text-[#F4F1EA]">
                {stop.title}
              </p>
              <p className="mt-2 text-[13px] leading-relaxed text-[#CFC8BC]">
                {stop.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
