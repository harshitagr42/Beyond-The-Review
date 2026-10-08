const STAGE_MESSAGES = {
  pii_redaction: "Redacting personal data",
  sentiment: "Analysing sentiment",
  embeddings: "Grouping reviews into themes",
  topics: "Grouping reviews into themes",
  validation: "Running quality checks",
  drift: "Running quality checks",
};

function remainingTimeSuffix(estimatedRemainingSeconds) {
  if (typeof estimatedRemainingSeconds !== "number" || Number.isNaN(estimatedRemainingSeconds)) {
    return "";
  }
  const minutes = Math.max(1, Math.round(estimatedRemainingSeconds / 60));
  return ` — about ${minutes} min left`;
}

function queuedMessage(queuePosition) {
  if (typeof queuePosition === "number" && queuePosition > 0) {
    return `Waiting in queue (position ${queuePosition})`;
  }
  return "Waiting in queue";
}

function processingMessage(payload) {
  const stage = payload?.stage;
  const base = STAGE_MESSAGES[stage] || "Analysing reviews";
  return `${base}${remainingTimeSuffix(payload?.estimated_remaining_seconds)}`;
}

/**
 * @param {object} payload
 * @returns {{ status: string, progress: number, message: string, error: object|null, queue_position: number|null, estimated_remaining_seconds: number|null }}
 */
export function adaptJobStatus(payload) {
  const status = payload?.status ?? "";
  const progress = payload?.progress_percent ?? 0;
  let message = "Analysing reviews";

  if (status === "QUEUED") {
    message = queuedMessage(payload?.queue_position);
  } else if (status === "PROCESSING") {
    message = processingMessage(payload);
  } else if (status === "COMPLETED") {
    message = "Analysis complete";
  } else if (status === "FAILED") {
    message = payload?.error?.message || "Processing failed. Please try again.";
  }

  return {
    status,
    progress,
    message,
    error: payload?.error ?? null,
    queue_position: payload?.queue_position ?? null,
    estimated_remaining_seconds: payload?.estimated_remaining_seconds ?? null,
  };
}

/**
 * @param {object} payload
 * @returns {{ positive: number, neutral: number, negative: number }}
 */
export function adaptSentimentBreakdown(payload) {
  const breakdown = payload?.sentiment_breakdown ?? {};
  return {
    positive: breakdown.positive ?? 0,
    neutral: breakdown.neutral ?? 0,
    negative: breakdown.negative ?? 0,
  };
}

function bucketPercent(count, reviewCount) {
  if (!reviewCount) return null;
  return Math.round((count / reviewCount) * 100);
}

/**
 * Maps backend trend points (counts per period) to the series TrendChart reads:
 * `{ labels, positive, neutral, negative }` as percentages. Empty buckets
 * (`review_count === 0`) become `null` so Chart.js renders them as gaps.
 *
 * @param {object} payload
 * @returns {{ labels: string[], positive: (number|null)[], neutral: (number|null)[], negative: (number|null)[] }}
 */
export function adaptTrends(payload) {
  const points = Array.isArray(payload?.data) ? payload.data : [];
  const labels = [];
  const positive = [];
  const neutral = [];
  const negative = [];

  for (const point of points) {
    labels.push(point.period_label ?? point.period_start ?? "");
    if (!point.review_count) {
      positive.push(null);
      neutral.push(null);
      negative.push(null);
      continue;
    }
    positive.push(bucketPercent(point.positive, point.review_count));
    neutral.push(bucketPercent(point.neutral, point.review_count));
    negative.push(bucketPercent(point.negative, point.review_count));
  }

  return { labels, positive, neutral, negative };
}

export function emptyTrends() {
  return { labels: [], positive: [], neutral: [], negative: [] };
}

/**
 * @param {object} payload
 * @returns {Array}
 */
export function adaptThemes(payload) {
  return Array.isArray(payload?.themes) ? payload.themes : [];
}

/**
 * Shape consumed if a caller renders VerbatimsDrawer-style cards:
 * `{ id, text, sentiment }` plus extra fields the API provides.
 *
 * @param {object} payload
 */
export function adaptVerbatims(payload) {
  const verbatims = Array.isArray(payload?.verbatims)
    ? payload.verbatims.map((v) => ({
        id: v.id,
        text: v.text,
        sentiment: v.sentiment,
        sentiment_score: v.sentiment_score,
        date: v.date ?? null,
        rating: v.rating ?? null,
        highlights: v.highlights ?? [],
      }))
    : [];

  return {
    theme: payload?.theme ?? null,
    page: payload?.page ?? 1,
    limit: payload?.limit ?? 20,
    total: payload?.total ?? verbatims.length,
    total_pages: payload?.total_pages ?? 1,
    verbatims,
  };
}

/**
 * Flattens governance metrics to the fields GovernanceBadges reads from `summary`,
 * while keeping the nested API objects for any future consumer.
 *
 * @param {object} payload
 */
export function adaptGovernanceMetrics(payload) {
  return {
    pii_redacted_count: payload?.pii?.total_redacted ?? 0,
    model_validation_accuracy: payload?.validation?.display ?? "",
    drift_status: payload?.drift?.display ?? "",
    pii: payload?.pii ?? null,
    validation: payload?.validation ?? null,
    drift: payload?.drift ?? null,
    models: payload?.models ?? null,
    data_quality: payload?.data_quality ?? null,
    audit_log: payload?.audit_log ?? [],
  };
}
