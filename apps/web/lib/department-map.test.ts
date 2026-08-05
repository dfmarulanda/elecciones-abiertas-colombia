import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  DANE_DEPARTMENT_BOUNDARY,
  REVIEWED_DEPARTMENT_CROSSWALK,
  reviewedDepartmentRows,
} from "./department-map";

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
