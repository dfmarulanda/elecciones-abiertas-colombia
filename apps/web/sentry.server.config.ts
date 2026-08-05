import * as Sentry from "@sentry/nextjs";

import { scrubSentryEvent } from "@/lib/sentry-privacy";

const dsn = process.env.SENTRY_DSN ?? process.env.NEXT_PUBLIC_SENTRY_DSN;

Sentry.init({
  dsn,
  enabled: Boolean(dsn),
  environment: process.env.VERCEL_ENV ?? process.env.NODE_ENV,
  release: process.env.NEXT_PUBLIC_ACTIVE_RELEASE,
  sendDefaultPii: false,
  tracesSampleRate: 0,
  beforeSend: scrubSentryEvent,
});
