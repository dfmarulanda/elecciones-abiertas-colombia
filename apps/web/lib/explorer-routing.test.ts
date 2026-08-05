import { describe, expect, it } from "vitest";
import {
  geographyRoute,
  isCanonicalMesaSegment,
  mesaRoute,
} from "./explorer-routing";

describe("canonical mesa routing", () => {
  it("keeps a mesa identifier intact in a locale route", () =>
    expect(mesaRoute("es", "2026-R2-11-001-001-003")).toBe(
      "/es/resultados/mesa/2026-R2-11-001-001-003",
    ));
  it("only identifies the explicit mesa catch-all shape as canonical", () => {
    expect(isCanonicalMesaSegment(["mesa", "x"])).toBe(true);
    expect(isCanonicalMesaSegment(["departamento", "CO-ANT"])).toBe(false);
  });
  it("preserves normalized release, election, and source in shared routes", () => {
    const filters = {
      release: "release-2026-r2",
      election: "presidencia-2026-segunda-vuelta",
      source: "scrutiny",
    };
    expect(mesaRoute("es", "MESA-001", filters)).toBe(
      "/es/resultados/mesa/MESA-001?release=release-2026-r2&election=presidencia-2026-segunda-vuelta&source=scrutiny",
    );
    expect(geographyRoute("en", "CO-11001", filters)).toBe(
      "/en/resultados/geografia/CO-11001?release=release-2026-r2&election=presidencia-2026-segunda-vuelta&source=scrutiny",
    );
  });
});
