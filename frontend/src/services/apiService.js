/**
 * API Service — Feedback & Review Analyzer
 * ────────────────────────────────────────
 * Client for the backend REST API (`/api/v1`).
 */

import { ApiError, requestBlob, requestJson } from "./httpClient";
import {
  adaptGovernanceMetrics,
  adaptJobStatus,
  adaptSentimentBreakdown,
  adaptThemes,
  adaptTrends,
  adaptVerbatims,
  emptyTrends,
} from "./adapters";

/** Last job id seen from upload or summary fetch; used when callers omit jobId. */
let activeJobId = null;

function rememberJobId(jobId) {
  if (jobId) activeJobId = jobId;
}

function resolveJobId(jobId) {
  return jobId ?? activeJobId;
}

function triggerBrowserDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Upload a review file (CSV / XLSX) and initiate processing pipeline.
 * @param {File|null} file - The file object from file input or drag-and-drop.
 * @returns {Promise<{job_id: string, status: string, message: string}>}
 */
export async function uploadFile(file) {
  let toUpload = file;
  if (!toUpload) {
    const sample = await requestBlob("/reviews/sample");
    toUpload = new File([sample], "sample_reviews.csv", { type: "text/csv" });
  }

  const formData = new FormData();
  formData.append("file", toUpload);

  const data = await requestJson("/reviews/upload", {
    method: "POST",
    body: formData,
  });

  rememberJobId(data.job_id);
  return {
    job_id: data.job_id,
    status: data.status,
    message: "Upload received",
  };
}

/**
 * Poll the processing status for a given job.
 * @param {string} jobId
 * @returns {Promise<{status: string, progress: number, message: string}>}
 */
export async function getJobStatus(jobId) {
  const id = resolveJobId(jobId);
  const data = await requestJson(`/jobs/${encodeURIComponent(id)}/status`);
  return adaptJobStatus(data);
}

/**
 * Fetch the full analytics summary (KPIs, breakdown, themes).
 * @param {string} jobId
 * @returns {Promise<object>}
 */
export async function getAnalyticsSummary(jobId) {
  const id = resolveJobId(jobId);
  rememberJobId(id);
  const data = await requestJson(`/analytics/summary?job_id=${encodeURIComponent(id)}`);
  if (data?.summary) {
    data.summary.pii_redacted_count = data.summary.pii_redacted_count ?? 0;
  }
  return data;
}

/**
 * Fetch sentiment percentage breakdown.
 * @param {string} jobId
 * @returns {Promise<{positive: number, neutral: number, negative: number}>}
 */
export async function getSentimentBreakdown(jobId) {
  const id = resolveJobId(jobId);
  const data = await requestJson(
    `/analytics/sentiment-breakdown?job_id=${encodeURIComponent(id)}`
  );
  return adaptSentimentBreakdown(data);
}

/**
 * Fetch time-series sentiment trend data.
 * @param {string} jobId
 * @param {"weekly"|"monthly"} interval
 * @returns {Promise<object>}
 */
export async function getTrends(jobId, interval = "weekly") {
  const id = resolveJobId(jobId);
  if (!id) return emptyTrends();
  try {
    const data = await requestJson(
      `/analytics/trends?job_id=${encodeURIComponent(id)}&interval=${encodeURIComponent(interval)}`
    );
    return adaptTrends(data);
  } catch (err) {
    if (err instanceof ApiError && err.status === 422 && err.code === "NO_DATE_DATA") {
      return emptyTrends();
    }
    throw err;
  }
}

/**
 * Fetch the list of extracted themes / complaint categories.
 * @param {string} jobId
 * @returns {Promise<Array>}
 */
export async function getThemes(jobId) {
  const id = resolveJobId(jobId);
  if (!id) return [];
  const data = await requestJson(`/themes?job_id=${encodeURIComponent(id)}`);
  return adaptThemes(data);
}

/**
 * Fetch verbatim quotes for a specific theme.
 * @param {string|object} themeId
 * @param {string} jobId
 * @param {number} page
 * @param {number} limit
 * @returns {Promise<object>}
 */
export async function getVerbatims(themeId, jobId, page = 1, limit = 20) {
  const id = resolveJobId(jobId);
  const actualThemeId =
    typeof themeId === "object" && themeId !== null
      ? themeId.id || themeId.theme_id
      : themeId;
  const params = new URLSearchParams({
    job_id: id || "",
    page: String(page),
    limit: String(limit),
  });
  const data = await requestJson(
    `/themes/${encodeURIComponent(actualThemeId)}/verbatims?${params.toString()}`
  );
  return adaptVerbatims(data);
}

/**
 * Fetch enterprise governance and quality metrics.
 * @param {string} jobId
 * @returns {Promise<object>}
 */
export async function getGovernanceMetrics(jobId) {
  const id = resolveJobId(jobId);
  const data = await requestJson(
    `/governance/metrics?job_id=${encodeURIComponent(id)}`
  );
  return adaptGovernanceMetrics(data);
}

/**
 * Download the backend sample reviews CSV as `sample_reviews.csv`.
 * @returns {Promise<void>}
 */
export async function downloadSampleCsv() {
  const blob = await requestBlob("/reviews/sample");
  triggerBrowserDownload(blob, "sample_reviews.csv");
}
