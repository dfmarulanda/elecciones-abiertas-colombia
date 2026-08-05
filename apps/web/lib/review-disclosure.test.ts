import { describe, expect, it } from "vitest";
import { fixtureAdapter } from "@/data/fixture-adapter";

describe("review disclosures", () => {
  it("makes the same permanent non-accusatory disclosure visible on every fixture signal", async () => {
    const release = await fixtureAdapter.getRelease();
    for (const signal of release.review_signals) {
      expect(signal.disclosure.es).toContain(
        "prioriza registros para revisión",
      );
      expect(signal.disclosure.en).toContain("prioritizes records for review");
    }
  });
});
