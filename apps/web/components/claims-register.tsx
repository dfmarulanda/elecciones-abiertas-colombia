import { grid, hexes } from "@/lib/hexes";

type Locale = "es" | "en";
type Text = (key: string) => string;

/**
 * #reclamos — the claims register, ported VERBATIM from the design source's
 * `sections/reclamos.html` markup and `dc-data.js`'s `claimsMid` fixture:
 * exact inline styles (not the app's ec-* Tailwind tokens — see the design
 * lane's `apps/web/app/[locale]/design.css`), the same six claims in the same
 * order, the same verdict tags and colours, the same `<details>` "Cómo se
 * verifica" / "Qué haría falta" disclosures.
 *
 * The six-vote figure is drawn by the same `hexes()`/`grid()` generator that
 * draws the 1,150-vote field in #conteo and the 190-vote mesa 003 field in
 * #mesa — not six copies of a hand-drawn placeholder path. `grid(6, 30, 6)`
 * and `hexes(..., 27)` match the source's `six = grid(6,30,6)` /
 * `sixD: hexes(six, 27)` exactly.
 *
 * All static content: this section reads no release and therefore never
 * degrades. Every string comes from the message bundle so both legs of the
 * wording gate (ES and EN) are checked. Per-claim colour (`fg`) is fixture
 * data, not language-dependent copy, so it is kept in code beside the claim
 * key rather than in the message bundle — matching how the design's own
 * `claimsMid` array embeds `fg` directly on each claim object.
 */

const SIX_VOTES = grid(6, 30, 6);
const SIX_VOTES_D = hexes(SIX_VOTES.points, 27);

const MID_CLAIMS = [
  { key: "atypical", fg: "#5F6300" },
  { key: "benford", fg: "#8A4B1E" },
  { key: "reportOrder", fg: "#5F6300" },
  { key: "moreVotesThanRegistered", fg: "#8A4B1E" },
] as const;

export function ClaimsRegister({ locale, t }: { locale: Locale; t: Text }) {
  return (
    <section
      id="reclamos"
      aria-label={t("claims.eyebrow")}
      data-screen-label={t("claims.eyebrow")}
      lang={locale}
      className="scroll-mt-24"
      style={{ maxWidth: 1440, margin: "0 auto", padding: "80px 46px 0" }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0,1fr) minmax(0,1.25fr)",
          gap: 64,
          alignItems: "baseline",
        }}
      >
        <div>
          <p className="mark" style={{ margin: 0, color: "#6B6259" }}>
            {t("claims.eyebrow")}
          </p>
          <h2 className="head" style={{ margin: "16px 0 0" }}>
            {t("claims.title")}
          </h2>
        </div>
        <p style={{ margin: 0, maxWidth: "42rem", fontSize: 17, lineHeight: 1.62, color: "#3E3831" }}>
          {t("claims.intro")}
        </p>
      </div>

      {/* Lead claim — the verifiable one, with the six-vote figure. */}
      <article
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0,1.1fr) minmax(0,1fr)",
          gap: 72,
          alignItems: "center",
          marginTop: 42,
          paddingTop: 34,
          borderTop: "1px solid #211E1E",
        }}
      >
        <div>
          <p className="mono" style={{ margin: 0, fontSize: 12, color: "#5F6300" }}>
            {t("claims.lead.verdict")}
          </p>
          <h3 className="claim" style={{ margin: "14px 0 0", fontSize: 32 }}>
            {t("claims.lead.claim")}
          </h3>
          <p style={{ margin: "20px 0 0", maxWidth: "34rem", fontSize: 17, lineHeight: 1.6, color: "#3E3831" }}>
            {t("claims.lead.answer")}
          </p>
          <details style={{ marginTop: 16 }}>
            <summary style={{ display: "inline-block", fontSize: 13, fontWeight: 600 }}>
              <span className="ul">{t("claims.methodLabel")}</span>
            </summary>
            <p style={{ margin: "14px 0 0", maxWidth: "34rem", fontSize: 14, lineHeight: 1.65, color: "#5A5148" }}>
              {t("claims.lead.method")}
            </p>
          </details>
        </div>
        <div style={{ background: "#151312", padding: "38px 44px 34px" }}>
          <svg
            viewBox={SIX_VOTES.vb}
            role="img"
            aria-label={t("claims.lead.figureAlt")}
            style={{ display: "block", width: "100%", height: "auto" }}
          >
            <path d={SIX_VOTES_D} fill="#C4FF00" />
          </svg>
          <p style={{ margin: "28px 0 0", fontSize: 15, lineHeight: 1.55, color: "#CFC8BC" }}>
            {t("claims.lead.figureNote")}
          </p>
        </div>
      </article>

      {/* Four mid claims, two per row. */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2,minmax(0,1fr))",
          gap: "0 72px",
          marginTop: 10,
        }}
      >
        {MID_CLAIMS.map((c) => (
          <article key={c.key} style={{ padding: "30px 0 32px", borderTop: "1px solid rgba(33,30,30,.16)" }}>
            <p className="mono" style={{ margin: 0, fontSize: 12, color: c.fg }}>
              {t(`claims.${c.key}.verdict`)}
            </p>
            <h3 className="claim" style={{ margin: "14px 0 0", fontSize: 24 }}>
              {t(`claims.${c.key}.claim`)}
            </h3>
            <p style={{ margin: "16px 0 0", fontSize: 16, lineHeight: 1.6, color: "#3E3831" }}>
              {t(`claims.${c.key}.answer`)}
            </p>
            <details style={{ marginTop: 14 }}>
              <summary style={{ display: "inline-block", fontSize: 13, fontWeight: 600 }}>
                <span className="ul">{t("claims.methodLabel")}</span>
              </summary>
              <p style={{ margin: "13px 0 0", fontSize: 14, lineHeight: 1.65, color: "#5A5148" }}>
                {t(`claims.${c.key}.detail`)}
              </p>
            </details>
          </article>
        ))}
      </div>

      {/* Final claim — no data to answer it, marked as such rather than forced into a verdict. */}
      <article
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0,1fr) minmax(0,1.1fr)",
          gap: 72,
          alignItems: "center",
          padding: "34px 0 0",
          borderTop: "1px solid #211E1E",
        }}
      >
        <div style={{ background: "#151312", padding: "44px 46px 38px" }}>
          <svg
            viewBox="0 0 240 210"
            role="img"
            aria-label={t("claims.unavailable.figureAlt")}
            style={{ display: "block", width: "100%", height: "auto" }}
          >
            <path
              d="M225 105L180 183L90 183L45 105L90 27L180 27Z"
              fill="none"
              stroke="#928979"
              strokeWidth={2}
              strokeDasharray="9 9"
            />
            <text
              x={135}
              y={114}
              textAnchor="middle"
              fontFamily="JetBrains Mono,ui-monospace,monospace"
              fontSize={15}
              fill="#928979"
            >
              {t("common.metricUnavailable").toLowerCase()}
            </text>
          </svg>
          <p style={{ margin: "26px 0 0", fontSize: 15, lineHeight: 1.55, color: "#CFC8BC" }}>
            {t("claims.unavailable.figureNote")}
          </p>
        </div>
        <div>
          <p className="mono" style={{ margin: 0, fontSize: 12, color: "#8A4B1E" }}>
            {t("claims.unavailable.verdict")}
          </p>
          <h3 className="claim" style={{ margin: "14px 0 0", fontSize: 32 }}>
            {t("claims.unavailable.claim")}
          </h3>
          <p style={{ margin: "20px 0 0", maxWidth: "36rem", fontSize: 17, lineHeight: 1.6, color: "#3E3831" }}>
            {t("claims.unavailable.answer")}
          </p>
          <details style={{ marginTop: 16 }}>
            <summary style={{ display: "inline-block", fontSize: 13, fontWeight: 600 }}>
              <span className="ul">{t("claims.methodLabelAlt")}</span>
            </summary>
            <p style={{ margin: "14px 0 0", maxWidth: "36rem", fontSize: 14, lineHeight: 1.65, color: "#5A5148" }}>
              {t("claims.unavailable.detail")}
            </p>
          </details>
        </div>
      </article>
    </section>
  );
}
