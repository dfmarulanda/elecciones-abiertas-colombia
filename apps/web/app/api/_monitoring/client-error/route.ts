import * as Sentry from "@sentry/nextjs";
import { createHash, randomUUID } from "node:crypto";
import type { NextRequest } from "next/server";

import {
  sanitizeClientErrorText,
  type ClientErrorKind,
} from "@/lib/client-error-reporting";

const kinds = new Set<ClientErrorKind>([
  "window_error",
  "unhandled_rejection",
  "react_global_error",
]);
const MAX_BODY_BYTES = 4_096;
const WINDOW_MS = 60_000;
const MAX_REPORTS_PER_WINDOW = 12;
const MAX_BUCKETS = 4_096;
const reportBuckets = new Map<string, { count: number; resetAt: number }>();
const bucketSalt = randomUUID();

function clientKey(request: NextRequest) {
  // This is intentionally ephemeral and only held in process memory. It is a
  // throttling key, not analytics or an identity record.
  const forwarded = request.headers.get("x-forwarded-for")?.split(",", 1)[0];
  const address =
    forwarded?.trim() || request.headers.get("x-real-ip") || "unknown";
  return createHash("sha256")
    .update(`${bucketSalt}:${address}`)
    .digest("base64url");
}

function permitReport(request: NextRequest, now = Date.now()) {
  const key = clientKey(request);
  const existing = reportBuckets.get(key);
  if (!existing || existing.resetAt <= now) {
    if (reportBuckets.size >= MAX_BUCKETS) {
      for (const [bucketKey, bucket] of reportBuckets) {
        if (bucket.resetAt <= now) reportBuckets.delete(bucketKey);
      }
      // The edge quota is authoritative. This bounded fallback must never
      // retain attacker-selected keys without limit inside an application VM.
      const oldestKey = reportBuckets.keys().next().value;
      if (reportBuckets.size >= MAX_BUCKETS && oldestKey)
        reportBuckets.delete(oldestKey);
    }
    reportBuckets.set(key, { count: 1, resetAt: now + WINDOW_MS });
    return true;
  }
  if (existing.count >= MAX_REPORTS_PER_WINDOW) return false;
  existing.count += 1;
  return true;
}

// Not used by application code. Keeping this narrow hook lets the route's
// memory bound be regression-tested without exposing telemetry state over HTTP.
export const clientErrorRateLimitTestHooks = {
  clear: () => reportBuckets.clear(),
  size: () => reportBuckets.size,
  permit: (request: NextRequest, now: number) => permitReport(request, now),
};

async function boundedJson(request: NextRequest): Promise<unknown> {
  if (!request.body) throw new Error("missing body");
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BODY_BYTES) throw new RangeError("body too large");
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return JSON.parse(new TextDecoder().decode(body));
}

function empty(status: number) {
  return new Response(null, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

export async function POST(request: NextRequest) {
  if (!process.env.SENTRY_DSN && !process.env.NEXT_PUBLIC_SENTRY_DSN) {
    return empty(204);
  }
  if (request.headers.get("sec-fetch-site") !== "same-origin")
    return empty(403);
  const origin = request.headers.get("origin");
  let sameOrigin = false;
  try {
    sameOrigin = Boolean(
      origin && new URL(origin).host === request.nextUrl.host,
    );
  } catch {
    sameOrigin = false;
  }
  if (
    !sameOrigin ||
    request.headers.get("content-type")?.split(";", 1)[0] !== "application/json"
  ) {
    return empty(403);
  }
  const contentLength = request.headers.get("content-length");
  if (contentLength !== null) {
    const length = Number(contentLength);
    if (!Number.isFinite(length) || length > MAX_BODY_BYTES) return empty(413);
  }
  let payload: unknown;
  try {
    payload = await boundedJson(request);
  } catch (error) {
    if (error instanceof RangeError) return empty(413);
    return empty(400);
  }
  if (!payload || typeof payload !== "object") return empty(400);
  const record = payload as Record<string, unknown>;
  if (!kinds.has(record.kind as ClientErrorKind)) return empty(400);
  if (!permitReport(request)) {
    return new Response(null, {
      status: 429,
      headers: { "Cache-Control": "no-store", "Retry-After": "60" },
    });
  }
  const name =
    typeof record.name === "string" &&
    /^[A-Za-z][A-Za-z0-9_.:-]{0,63}$/.test(record.name)
      ? record.name
      : "UnknownError";
  const kind = record.kind as ClientErrorKind;
  Sentry.captureMessage(
    `Client ${kind}: ${sanitizeClientErrorText(record.message, 240)}`,
    {
      level: "error",
      tags: { client_error_kind: kind, client_error_name: name },
      extra: {
        stack: sanitizeClientErrorText(record.stack, 2_000),
        path: sanitizeClientErrorText(record.path, 300),
      },
    },
  );
  return empty(204);
}
