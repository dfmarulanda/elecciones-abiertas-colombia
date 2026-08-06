"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

const NAV_IDS = [
  "conteo",
  "reclamos",
  "comparacion",
  "mesa",
  "territorios",
  "proceso",
  "bitacora",
  "datos",
] as const;
type NavId = (typeof NAV_IDS)[number];

/**
 * The design's own header chrome from `template-body.html`'s `<header>` --
 * ported with its exact inline style values, MINUS the wordmark, the skip
 * link and the hamburger glyph. Those three already render at the very top
 * of every route via the app's persistent `SiteShell`
 * (`apps/web/components/site-shell.tsx`), so reproducing them again here
 * would stack two wordmarks and two "skip to content" links directly on top
 * of each other -- chrome duplication, not fidelity.
 *
 * What genuinely does NOT exist anywhere else in the app is the source's
 * live "current section" readout and its 8-item index of the page's own
 * in-page anchors (#conteo, #reclamos, ...) with scroll-spy highlighting --
 * SiteShell's own index panel links to *other routes* (/resultados,
 * /analitica, ...), not to these anchors. That is the part transcribed here,
 * verbatim, plus the source's page-scroll progress rail.
 *
 * It sticks at `var(--sticky-top)` -- i.e. directly beneath SiteShell's own
 * sticky header -- using the app's existing `--header-h` / `--header-progress-h`
 * tokens (globals.css), which happen to sum to exactly the source's own
 * hard-coded `top:66px` for its single header. Because this app has TWO
 * stacked sticky bars where the source design has one, anything sized off
 * "the header's height" downstream (the bitácora track's sticky stage) uses
 * `calc(var(--sticky-top) * 2)` instead of the source's literal `66px` -- see
 * `bitacora-track.tsx`.
 */
export function DesignHeader() {
  const t = useTranslations();
  const [active, setActive] = useState<NavId>("conteo");
  const [progress, setProgress] = useState(0);
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    let frame = 0;
    const tick = () => {
      if (!alive) return;
      frame = requestAnimationFrame(tick);
      if (document.hidden) return;

      const doc = document.documentElement;
      const max = doc.scrollHeight - doc.clientHeight;
      const p = max > 0 ? Math.min(1, Math.max(0, doc.scrollTop / max)) : 0;

      let bestId: NavId = NAV_IDS[0];
      let bestTop = -Infinity;
      for (const id of NAV_IDS) {
        const el = document.getElementById(id);
        if (!el) continue;
        const top = el.getBoundingClientRect().top;
        if (top <= 140 && top > bestTop) {
          bestTop = top;
          bestId = id;
        }
      }

      setProgress((prev) => (Math.abs(prev - p) > 0.0015 ? p : prev));
      setActive((prev) => (prev !== bestId ? bestId : prev));
    };
    frame = requestAnimationFrame(tick);
    return () => {
      alive = false;
      cancelAnimationFrame(frame);
    };
  }, []);

  const activeIndex = Math.max(0, NAV_IDS.indexOf(active));
  const currentLabel = `${String(activeIndex + 1).padStart(2, "0")} · ${t(`homeHeader.items.${active}.label`)}`;

  return (
    <div
      style={{
        position: "sticky",
        top: "var(--sticky-top)",
        zIndex: 39,
        background: "rgba(244,241,234,.94)",
        backdropFilter: "blur(14px)",
        borderBottom: "1px solid #211E1E",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 32,
          maxWidth: 1440,
          margin: "0 auto",
          padding: "0 46px",
          height: 64,
        }}
      >
        <p
          className="mono"
          style={{
            margin: 0,
            fontSize: 12,
            color: "#211E1E",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {currentLabel}
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: 20, flex: "none" }}>
          <button
            type="button"
            onClick={() => setNavOpen((v) => !v)}
            aria-expanded={navOpen}
            aria-controls="eac-design-index"
            className="mono"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 9,
              border: "1px solid #211E1E",
              background: "none",
              padding: "7px 14px",
              font: "inherit",
              fontSize: 13,
              cursor: "pointer",
              whiteSpace: "nowrap",
              color: "#211E1E",
            }}
          >
            <span aria-hidden="true" style={{ display: "grid", gap: 2.5 }}>
              <span style={{ display: "block", width: 13, height: 1.5, background: "#211E1E" }} />
              <span style={{ display: "block", width: 13, height: 1.5, background: "#211E1E" }} />
              <span style={{ display: "block", width: 13, height: 1.5, background: "#211E1E" }} />
            </span>
            {navOpen ? t("nav.indexClose") : t("nav.index")}
          </button>
        </div>
      </div>

      <div style={{ height: 2, background: "rgba(33,30,30,.12)" }} aria-hidden="true">
        <div
          style={{
            height: "100%",
            width: `${(progress * 100).toFixed(2)}%`,
            background: "#C4FF00",
          }}
        />
      </div>

      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: "100%",
          background: "#151312",
          borderBottom: "1px solid #211E1E",
          opacity: navOpen ? 1 : 0,
          transform: navOpen ? "translateY(0)" : "translateY(-10px)",
          pointerEvents: navOpen ? "auto" : "none",
          transition: "opacity 240ms cubic-bezier(.2,.7,.1,1), transform 240ms cubic-bezier(.2,.7,.1,1)",
        }}
      >
        <nav
          id="eac-design-index"
          aria-label={t("nav.indexPanel")}
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4,minmax(0,1fr))",
            gap: "1px 34px",
            maxWidth: 1440,
            margin: "0 auto",
            padding: "30px 46px 34px",
          }}
        >
          {NAV_IDS.map((id, i) => {
            const isActive = id === active;
            return (
              <a
                key={id}
                href={`#${id}`}
                onClick={() => setNavOpen(false)}
                className="eac-index-link"
                style={{
                  display: "block",
                  padding: "14px 0 16px",
                  borderTop: `1px solid ${isActive ? "#C4FF00" : "rgba(244,241,234,.16)"}`,
                  color: isActive ? "#F4F1EA" : "#928979",
                }}
              >
                <span
                  className="mono"
                  style={{ display: "block", fontSize: 11, color: isActive ? "#C4FF00" : "#6B6259" }}
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span
                  style={{
                    display: "block",
                    marginTop: 7,
                    fontSize: 19,
                    fontWeight: 600,
                    letterSpacing: "-.015em",
                    lineHeight: 1.2,
                  }}
                >
                  {t(`homeHeader.items.${id}.label`)}
                </span>
                <span
                  style={{
                    display: "block",
                    marginTop: 6,
                    fontSize: 13.5,
                    lineHeight: 1.45,
                    color: "#928979",
                  }}
                >
                  {t(`homeHeader.items.${id}.desc`)}
                </span>
              </a>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
