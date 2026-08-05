import * as Sentry from "@sentry/nextjs";
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clientErrorRateLimitTestHooks, POST } from "./route";

vi.mock("@sentry/nextjs", () => ({ captureMessage: vi.fn() }));

const endpoint = "https://viewer.example.test/api/_monitoring/client-error";

function request(
  origin: string,
  body: Record<string, unknown>,
  options: HeadersInit = {},
) {
  return new NextRequest(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      origin,
      "sec-fetch-site": "same-origin",
      ...options,
    },
    body: JSON.stringify(body),
  });
}

describe("client error relay", () => {
  beforeEach(() => {
    process.env.SENTRY_DSN = "https://public@example.test/1";
  });

  afterEach(() => {
    delete process.env.SENTRY_DSN;
    clientErrorRateLimitTestHooks.clear();
    vi.clearAllMocks();
  });

  it("rejects cross-origin reports", async () => {
    const response = await POST(
      request("https://attacker.example.test", {
        kind: "window_error",
        name: "TypeError",
        message: "failure",
      }),
    );
    expect(response.status).toBe(403);
    expect(Sentry.captureMessage).not.toHaveBeenCalled();
  });

  it("requires a same-origin browser fetch signal", async () => {
    const response = await POST(
      request(
        "https://viewer.example.test",
        { kind: "window_error" },
        { "sec-fetch-site": "cross-site" },
      ),
    );
    expect(response.status).toBe(403);
  });

  it("rejects bodies over the hard byte limit", async () => {
    const response = await POST(
      request("https://viewer.example.test", {
        kind: "window_error",
        message: "x".repeat(5_000),
      }),
    );
    expect(response.status).toBe(413);
  });

  it("caps and deterministically evicts ephemeral limiter buckets", () => {
    const now = 1_000;
    clientErrorRateLimitTestHooks.clear();
    for (let index = 0; index < 4_097; index += 1) {
      const candidate = request(
        "https://viewer.example.test",
        { kind: "window_error" },
        { "x-forwarded-for": `198.51.100.${index}` },
      );
      expect(clientErrorRateLimitTestHooks.permit(candidate, now)).toBe(true);
    }
    expect(clientErrorRateLimitTestHooks.size()).toBe(4_096);
    // At a later window boundary, expired entries are pruned before new keys.
    const fresh = request(
      "https://viewer.example.test",
      { kind: "window_error" },
      { "x-forwarded-for": "203.0.113.1" },
    );
    expect(clientErrorRateLimitTestHooks.permit(fresh, now + 60_001)).toBe(
      true,
    );
    expect(clientErrorRateLimitTestHooks.size()).toBe(1);
  });

  it("relays a bounded, scrubbed same-origin diagnostic", async () => {
    const response = await POST(
      request("https://viewer.example.test", {
        kind: "react_global_error",
        name: "TypeError",
        message:
          "Failed https://viewer.example.test/es?email=voter@example.test from 10.0.0.1 voter@example.test",
        stack: "stack",
        path: "/es/resultados",
      }),
    );
    expect(response.status).toBe(204);
    expect(Sentry.captureMessage).toHaveBeenCalledOnce();
    const [message, context] = vi.mocked(Sentry.captureMessage).mock.calls[0]!;
    expect(message).toBe(
      "Client react_global_error: Failed https://viewer.example.test/es from [redacted-ip] [redacted-email]",
    );
    expect(context).toMatchObject({
      tags: {
        client_error_kind: "react_global_error",
        client_error_name: "TypeError",
      },
      extra: { path: "/es/resultados", stack: "stack" },
    });
  });
});
