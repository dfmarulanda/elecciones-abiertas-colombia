import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  DANE_DEPARTMENT_BOUNDARY,
  EXTRATERRITORIAL_GEOGRAPHY_IDS,
  REVIEWED_DEPARTMENT_CROSSWALK,
  partitionDepartments,
  reviewedDepartmentRows,
} from "./department-map";

type Rollup = { department_rollup: { id: string; code: string; name: string }[] };

const realDepartments = (
  JSON.parse(
    readFileSync(
      path.resolve(process.cwd(), "../../data/fixtures/preliminary-release.json"),
      "utf8",
    ),
  ) as Rollup
).department_rollup.map((row) => ({
  geographyId: row.id,
  label: row.name,
  value: "1",
}));

describe("reviewed department map crosswalk", () => {
  it("maps only explicit source identifiers", () => {
    expect(REVIEWED_DEPARTMENT_CROSSWALK["CO-ANT"]).toBe("05");
    expect(REVIEWED_DEPARTMENT_CROSSWALK["r2:dep:16"]).toBe("11");
    expect(REVIEWED_DEPARTMENT_CROSSWALK.ANTIOQUIA).toBeUndefined();
    expect(REVIEWED_DEPARTMENT_CROSSWALK["scope:999"]).toBeUndefined();
  });

  it("omits unknown and duplicate geography instead of guessing", () => {
    expect(
      reviewedDepartmentRows([
        { geographyId: "unknown", label: "Antioquia", value: "9" },
        { geographyId: "CO-ANT", label: "Antioquia", value: "2" },
        { geographyId: "scope:01", label: "Different name", value: "3" },
      ]),
    ).toEqual([
      expect.objectContaining({
        daneCode: "05",
        daneName: "Antioquia",
        value: "2",
      }),
    ]);
  });

  it("binds the runtime derivative to its declared hash and the official source URL", () => {
    const bytes = readFileSync(
      path.resolve(
        process.cwd(),
        "public/maps/dane-departments-2025-simplified.geojson",
      ),
    );
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(
      DANE_DEPARTMENT_BOUNDARY.derivativeSha256,
    );
    expect(DANE_DEPARTMENT_BOUNDARY.sourceResponseSha256).toMatch(
      /^[a-f0-9]{64}$/,
    );
    expect(DANE_DEPARTMENT_BOUNDARY.sourceUrl).toContain(
      "geoportal.dane.gov.co",
    );
    expect(DANE_DEPARTMENT_BOUNDARY.sourceUrl).toContain("&outFields=");
    expect(DANE_DEPARTMENT_BOUNDARY.derivativeTransformVersion).toContain(
      "max-allowable-offset",
    );
  });
});

describe("every real department is accounted for", () => {
  it("leaves nothing unmapped and nothing silently dropped", () => {
    // The failure this guards: reviewedDepartmentRows omits what it cannot map,
    // so a crosswalk gap removes a department's votes from the map with no
    // error raised anywhere.
    const { mapped, extraterritorial, unmapped } =
      partitionDepartments(realDepartments);
    expect(realDepartments).toHaveLength(34);
    expect(unmapped).toEqual([]);
    expect(mapped.length + extraterritorial.length).toBe(realDepartments.length);
    expect(mapped).toHaveLength(33);
  });

  it("keeps CONSULADOS off the map instead of on an island", () => {
    const { mapped, extraterritorial } = partitionDepartments(realDepartments);
    expect(extraterritorial.map((row) => row.geographyId)).toEqual(["scope:88"]);
    expect(mapped.some((row) => row.geographyId === "scope:88")).toBe(false);
    // DANE 88 is the San Andrés archipelago. Mapping the exterior by code
    // equality would paint 613,049 overseas votes onto a Caribbean island.
    expect(REVIEWED_DEPARTMENT_CROSSWALK["scope:88"]).toBeUndefined();
    expect(EXTRATERRITORIAL_GEOGRAPHY_IDS.has("scope:88")).toBe(true);
  });

  it("never resolves a department by raw code equality", () => {
    // Registraduría 05 is BOLÍVAR, DANE 05 is ANTIOQUIA.
    // Registraduría 13 is CÓRDOBA, DANE 13 is BOLÍVAR.
    expect(REVIEWED_DEPARTMENT_CROSSWALK["scope:01"]).toBe("05");
    expect(REVIEWED_DEPARTMENT_CROSSWALK["scope:05"]).toBe("13");
    expect(REVIEWED_DEPARTMENT_CROSSWALK["scope:13"]).toBe("23");
  });

  it("gives each mapped department a distinct polygon", () => {
    const codes = reviewedDepartmentRows(realDepartments).map(
      (row) => row.daneCode,
    );
    expect(new Set(codes).size).toBe(codes.length);
  });
});
