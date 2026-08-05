import { describe, expect, it } from "vitest";
import { formatMetricValue, type MetricStatusLabels } from "./metric-value";

const labels: MetricStatusLabels = {
  observed: "Observed",
  unknown: "Unknown",
  unavailable: "Unavailable",
  not_applicable: "Not applicable",
};

describe("MetricValue formatting", () => {
  it("keeps observed zero numeric and exposes its status", () => {
    expect(
      formatMetricValue({ value: 0, status: "observed" }, "en", labels),
    ).toEqual({ display: "0", statusLabel: "Observed" });
  });

  it.each([
    ["unknown", "Unknown"],
    ["unavailable", "Unavailable"],
    ["not_applicable", "Not applicable"],
  ] as const)(
    "renders %s as its localized state, not an em dash",
    (status, display) => {
      expect(formatMetricValue({ value: null, status }, "en", labels)).toEqual({
        display,
        statusLabel: display,
      });
    },
  );
});
