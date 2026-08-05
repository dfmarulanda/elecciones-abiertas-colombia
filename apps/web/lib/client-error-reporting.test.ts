import { describe, expect, it } from "vitest";

import { sanitizeClientErrorText } from "./client-error-reporting";

describe("client error privacy", () => {
  it("removes query strings, email addresses, and IP addresses", () => {
    const scrubbed = sanitizeClientErrorText(
      "Failed at https://example.test/results?email=voter@example.test from 192.168.1.1 voter@example.test",
      500,
    );
    expect(scrubbed).toBe(
      "Failed at https://example.test/results from [redacted-ip] [redacted-email]",
    );
  });

  it("caps diagnostic text", () => {
    expect(sanitizeClientErrorText("x".repeat(20), 8)).toBe("xxxxxxxx");
  });
});
