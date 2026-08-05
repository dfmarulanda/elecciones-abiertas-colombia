import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(value: number | null | undefined, locale: string) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat(locale).format(value);
}

export function formatPercent(
  value: number | null | undefined,
  locale: string,
) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat(locale, {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

/** Never round an incomplete reporting count up to 100%. */
export function formatCompletionPercent(
  reported: number,
  expected: number,
  locale: string,
) {
  const complete = expected > 0 && reported === expected;
  return new Intl.NumberFormat(locale, {
    style: "percent",
    minimumFractionDigits: complete ? 0 : 3,
    maximumFractionDigits: complete ? 1 : 3,
  }).format(expected > 0 ? reported / expected : 0);
}

export function formatDate(value: string, locale: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}
