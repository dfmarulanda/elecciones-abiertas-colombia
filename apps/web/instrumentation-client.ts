import { reportClientError } from "@/lib/client-error-reporting";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn && typeof window !== "undefined") {
  window.addEventListener("error", (event) => {
    reportClientError("window_error", event.error ?? event.message);
  });
  window.addEventListener("unhandledrejection", (event) => {
    reportClientError("unhandled_rejection", event.reason);
  });
}

// Navigation tracing is intentionally disabled (tracesSampleRate is zero).
export const onRouterTransitionStart = () => undefined;
