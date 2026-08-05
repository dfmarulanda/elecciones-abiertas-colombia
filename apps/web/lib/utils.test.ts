import { describe, expect, it } from "vitest";
import { formatCompletionPercent, formatNumber } from "./utils";

describe("metric formatting", () => {
  it("keeps observed zero distinct from unavailable data", () => {
    expect(formatNumber(0, "es-CO")).toBe("0");
    expect(formatNumber(null, "es-CO")).toBe("—");
  });

  it("does not round incomplete completion to 100% in either locale", () => {
    expect(formatCompletionPercent(122_017, 122_020, "es-CO")).toBe("99,998%");
    expect(formatCompletionPercent(122_017, 122_020, "en-US")).toBe("99.998%");
    expect(formatCompletionPercent(122_020, 122_020, "es-CO")).toBe("100%");
  });
});
