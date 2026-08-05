export type MetricStatus =
  "observed" | "unknown" | "unavailable" | "not_applicable";

export type MetricValue = { value: number | null; status: MetricStatus };

export type MetricStatusLabels = Record<MetricStatus, string>;

export function formatMetricValue(
  metric: MetricValue,
  locale: string,
  labels: MetricStatusLabels,
) {
  const statusLabel = labels[metric.status];
  if (metric.status !== "observed")
    return { display: statusLabel, statusLabel };
  return {
    display:
      metric.value === null
        ? labels.unknown
        : new Intl.NumberFormat(locale).format(metric.value),
    statusLabel,
  };
}
