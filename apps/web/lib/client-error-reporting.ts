export type ClientErrorKind =
  "window_error" | "unhandled_rejection" | "react_global_error";

const emailPattern = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;
const ipv4Pattern = /\b(?:\d{1,3}\.){3}\d{1,3}\b/g;
const urlPattern = /https?:\/\/[^\s)"']+/gi;

export function sanitizeClientErrorText(value: unknown, limit: number): string {
  const raw =
    typeof value === "string" ? value : String(value ?? "Unknown error");
  const scrubbed = raw
    .replace(urlPattern, (candidate) => {
      try {
        const parsed = new URL(candidate);
        return `${parsed.origin}${parsed.pathname}`;
      } catch {
        return "[url]";
      }
    })
    .replace(emailPattern, "[redacted-email]")
    .replace(ipv4Pattern, "[redacted-ip]");
  return scrubbed.slice(0, limit);
}

function errorName(value: unknown): string {
  const candidate = value instanceof Error ? value.name : "UnknownError";
  return /^[A-Za-z][A-Za-z0-9_.:-]{0,63}$/.test(candidate)
    ? candidate
    : "UnknownError";
}

export function reportClientError(kind: ClientErrorKind, value: unknown): void {
  if (
    !process.env.NEXT_PUBLIC_SENTRY_DSN ||
    typeof window === "undefined" ||
    typeof navigator === "undefined"
  ) {
    return;
  }
  const payload = JSON.stringify({
    kind,
    name: errorName(value),
    message: sanitizeClientErrorText(
      value instanceof Error ? value.message : value,
      240,
    ),
    stack: sanitizeClientErrorText(
      value instanceof Error ? value.stack : undefined,
      2_000,
    ),
    path: window.location.pathname.slice(0, 300),
  });
  if (
    typeof navigator.sendBeacon === "function" &&
    navigator.sendBeacon(
      "/api/_monitoring/client-error",
      new Blob([payload], { type: "application/json" }),
    )
  ) {
    return;
  }
  void fetch("/api/_monitoring/client-error", {
    method: "POST",
    body: payload,
    headers: { "Content-Type": "application/json" },
    credentials: "omit",
    keepalive: true,
  });
}
