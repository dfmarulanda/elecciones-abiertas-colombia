import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { describe, expect, it } from "vitest";
import { Dot, StatusBadge } from "./ui";

describe("core status badge", () => {
  it("renders explicit text alongside its non-color status marker", () => {
    const html = renderToStaticMarkup(
      <StatusBadge tone="fixture">
        <Dot />
        Synthetic fixture
      </StatusBadge>,
    );
    expect(html).toContain("Synthetic fixture");
    expect(html).toContain('aria-hidden="true"');
  });
});
