import { describe, expect, it } from "vitest";
import { build, grid, hexes } from "./hexes";

// Expected strings below were produced by running the design's own
// `dc-data.js` generator (unmodified) against the same inputs, so this test
// locks the port to byte-identical geometry, not just "close enough" hexagons.

describe("grid", () => {
  it("lays out six cells the way the reclamos figure needs them", () => {
    const six = grid(6, 30, 6);
    expect(six.vb).toBe("0 0 285.0 86.0");
    expect(six.points).toHaveLength(6);
    expect(six.points[0]).toEqual([30, 30]);
  });
});

describe("hexes", () => {
  it("draws the six reclamos hexagons byte-identical to the source generator", () => {
    const six = grid(6, 30, 6);
    expect(hexes(six.points, 27)).toBe(
      "M57.0 30.0L43.5 53.4L16.5 53.4L3.0 30.0L16.5 6.6L43.5 6.6Z" +
        "M102.0 56.0L88.5 79.4L61.5 79.4L48.0 56.0L61.5 32.6L88.5 32.6Z" +
        "M147.0 30.0L133.5 53.4L106.5 53.4L93.0 30.0L106.5 6.6L133.5 6.6Z" +
        "M192.0 56.0L178.5 79.4L151.5 79.4L138.0 56.0L151.5 32.6L178.5 32.6Z" +
        "M237.0 30.0L223.5 53.4L196.5 53.4L183.0 30.0L196.5 6.6L223.5 6.6Z" +
        "M282.0 56.0L268.5 79.4L241.5 79.4L228.0 56.0L241.5 32.6L268.5 32.6Z",
    );
  });
});

describe("build", () => {
  const mesa003 = { h: 108, r: 82, disp: 6 };
  const mini = build(mesa003, 17, 14);

  it("sizes the viewBox to fit mesa 003's 190-vote grid", () => {
    expect(mini.vb).toBe("0 0 365.5 431.5");
  });

  it("splits the 190 votes into 102 undisputed Horizonte, 82 Río and 6 disputed", () => {
    expect(mini.dH.match(/M/g)).toHaveLength(102);
    expect(mini.dR.match(/M/g)).toHaveLength(82);
    expect(mini.dD.match(/M/g)).toHaveLength(6);
    expect(mini.dDot.match(/M/g)).toHaveLength(6);
  });

  it("draws the disputed cells byte-identical to the source generator", () => {
    expect(mini.dD).toBe(
      "M134.8 223.1L126.9 236.8L111.1 236.8L103.2 223.1L111.1 209.4L126.9 209.4Z" +
        "M160.3 237.8L152.4 251.5L136.6 251.5L128.7 237.8L136.6 224.1L152.4 224.1Z" +
        "M185.8 223.1L177.9 236.8L162.1 236.8L154.2 223.1L162.1 209.4L177.9 209.4Z" +
        "M211.3 237.8L203.4 251.5L187.6 251.5L179.7 237.8L187.6 224.1L203.4 224.1Z" +
        "M236.8 223.1L228.9 236.8L213.1 236.8L205.2 223.1L213.1 209.4L228.9 209.4Z" +
        "M262.3 237.8L254.4 251.5L238.6 251.5L230.7 237.8L238.6 224.1L254.4 224.1Z",
    );
    expect(mini.dDot).toBe(
      "M123.7 223.1L121.4 227.2L116.6 227.2L114.3 223.1L116.6 219.0L121.4 219.0Z" +
        "M149.2 237.8L146.9 241.9L142.1 241.9L139.8 237.8L142.1 233.7L146.9 233.7Z" +
        "M174.7 223.1L172.4 227.2L167.6 227.2L165.3 223.1L167.6 219.0L172.4 219.0Z" +
        "M200.2 237.8L197.9 241.9L193.1 241.9L190.8 237.8L193.1 233.7L197.9 233.7Z" +
        "M225.7 223.1L223.4 227.2L218.6 227.2L216.3 223.1L218.6 219.0L223.4 219.0Z" +
        "M251.2 237.8L248.9 241.9L244.1 241.9L241.8 237.8L244.1 233.7L248.9 233.7Z",
    );
  });

  it("has no disputed cells and no dot when a mesa carries no disp", () => {
    const clean = build({ h: 3, r: 2 }, 17, 14);
    expect(clean.dD).toBe("");
    expect(clean.dDot).toBe("");
    expect(clean.dH.match(/M/g)).toHaveLength(3);
    expect(clean.dR.match(/M/g)).toHaveLength(2);
  });
});
