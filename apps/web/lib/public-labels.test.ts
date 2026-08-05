import { describe, expect, it } from "vitest";

import {
  directChildrenLabel,
  geographyLevelLabel,
  legalStatusLabel,
  publicResultLabels,
  sourceTypeLabel,
} from "./public-labels";

describe("public normalized labels", () => {
  it("localizes territorial, source, and legal enums", () => {
    expect(geographyLevelLabel("es", "municipality")).toBe("Municipio");
    expect(geographyLevelLabel("en", "polling_place")).toBe("Polling place");
    expect(sourceTypeLabel("es", "scrutiny")).toBe("Escrutinio");
    expect(sourceTypeLabel("en", "scrutiny")).toBe("Scrutiny");
    expect(legalStatusLabel("es", "official_scrutiny")).toBe(
      "Escrutinio oficial",
    );
    expect(publicResultLabels("es").geography.mesa).toBe("Mesa");
    expect(publicResultLabels("en").source.scrutiny).toBe("Scrutiny");
  });

  it("uses grammatical direct-child counts", () => {
    expect(directChildrenLabel("es", 1)).toBe("1 unidad hija");
    expect(directChildrenLabel("es", 2)).toBe("2 unidades hijas");
    expect(directChildrenLabel("en", 1)).toBe("1 direct child");
  });
});
