import { describe, expect, it } from "vitest";
import {
  fixtureResultCsv,
  readResultFilters,
  resultHref,
  serializeApiResultFilters,
  serializeResultFilters,
} from "./result-filters";

describe("result filter URLs", () => {
  it("keeps a stable, shareable filter order", () =>
    expect(
      serializeResultFilters({
        candidate: "candidatura-rio",
        source: "pre_count",
        ballot: "2",
      }),
    ).toBe("source=pre_count&candidate=candidatura-rio&ballot=2"));
  it("drops empty and repeated query values", () =>
    expect(
      readResultFilters({ source: ["bad", "pre_count"], geography: "  " }),
    ).toEqual({}));
  it("builds an exact CSV view link", () =>
    expect(resultHref("es", { geography: "CO-ANT" }, "csv")).toBe(
      "/es/resultados?geography=CO-ANT&format=csv",
    ));
  it("maps browser filters exactly to the live CSV endpoint", () =>
    expect(
      serializeApiResultFilters(
        {
          source: "pre_count",
          geography: "CO-ANT",
          candidate: "candidate-1",
        },
        undefined,
        "release-1",
      ),
    ).toBe(
      "format=csv&source_type=pre_count&geography_id=CO-ANT&candidate_id=candidate-1&data_version=release-1",
    ));
  it("renders only the selected synthetic rows and neutralizes spreadsheet formulas", () => {
    const csv = fixtureResultCsv(
      [
        {
          mesa: "mesa-1",
          geography: "=unsafe",
          department: "Bogotá",
          source: "pre_count",
          candidateId: "candidate-1",
          candidate: 'Nombre "uno"',
          ballot: "1",
          votes: null,
          votesStatus: "unknown",
          hash: "a".repeat(64),
        },
      ],
      "fixture-v1",
    );
    expect(csv).toContain('"\'=unsafe"');
    expect(csv).toContain('"Nombre ""uno"""');
    expect(csv).toContain('"unknown","fixture-v1"');
  });
});
