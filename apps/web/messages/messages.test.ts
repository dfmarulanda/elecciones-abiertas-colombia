import { describe, expect, it } from "vitest";
import en from "./en.json";
import es from "./es.json";

function leaves(value: unknown, prefix = ""): string[] {
  if (typeof value === "string") return [prefix];
  if (!value || typeof value !== "object") return [];
  return Object.entries(value).flatMap(([key, nested]) =>
    leaves(nested, prefix ? `${prefix}.${key}` : key),
  );
}

describe("locale messages", () => {
  it("has matching Spanish and English message keys", () => {
    expect(leaves(en).sort()).toEqual(leaves(es).sort());
  });
});
