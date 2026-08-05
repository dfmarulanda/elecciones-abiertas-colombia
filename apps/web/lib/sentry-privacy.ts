import type { ErrorEvent } from "@sentry/nextjs";

/** Keep error telemetry useful without visitor identifiers or URL query values. */
export function scrubSentryEvent(event: ErrorEvent): ErrorEvent {
  event.user = undefined;
  if (event.request) {
    event.request.cookies = undefined;
    event.request.data = undefined;
    event.request.headers = undefined;
    event.request.query_string = undefined;
    if (event.request.url) {
      event.request.url = event.request.url.split(/[?#]/, 1)[0];
    }
  }
  return event;
}
