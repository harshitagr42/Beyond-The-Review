/**
 * API Service — Feedback & Review Analyzer
 * ────────────────────────────────────────
 * Abstraction layer for all API calls.
 *
 * Currently fully wired to the standalone mock API handlers (/src/api/mock/).
 * Delivers realistic simulated server responses with 800ms artificial network latency.
 * When you are ready to build and connect the real backend, replace these mock calls
 * with fetch/axios calls to your REST endpoints.
 */

import {
  mockUploadFile,
  mockGetJobStatus,
  mockGetSummary,
  mockGetSentimentBreakdown,
  mockGetTrends,
  mockGetThemes,
  mockGetVerbatims,
  mockGetGovernanceMetrics,
} from "../api/mock/mockHandlers";

/* ═══════════════════════════════════════════════════
   Public API Surface (Mock-Driven)
   ═══════════════════════════════════════════════════ */

/**
 * Upload a review file (CSV / XLSX) and initiate processing pipeline.
 * @param {File|null} file - The file object from file input or drag-and-drop.
 * @returns {Promise<{job_id: string, status: string, message: string}>}
 */
export async function uploadFile(file) {
  // Simulates POST /api/v1/reviews/upload (multipart/form-data)
  return mockUploadFile(file);
}

/**
 * Poll the processing status for a given job.
 * @param {string} jobId
 * @returns {Promise<{status: string, progress: number, message: string}>}
 */
export async function getJobStatus(jobId) {
  // Simulates GET /api/v1/jobs/{jobId}/status
  return mockGetJobStatus(jobId);
}

/**
 * Fetch the full analytics summary (KPIs, breakdown, themes).
 * @param {string} jobId
 * @returns {Promise<object>}
 */
export async function getAnalyticsSummary(jobId) {
  // Simulates GET /api/v1/analytics/summary?job_id={jobId}
  return mockGetSummary(jobId);
}

/**
 * Fetch sentiment percentage breakdown.
 * @param {string} jobId
 * @returns {Promise<{positive: number, neutral: number, negative: number}>}
 */
export async function getSentimentBreakdown(jobId) {
  // Simulates GET /api/v1/analytics/sentiment-breakdown?job_id={jobId}
  return mockGetSentimentBreakdown(jobId);
}

/**
 * Fetch time-series sentiment trend data.
 * @param {string} jobId
 * @param {"weekly"|"monthly"} interval
 * @returns {Promise<object>}
 */
export async function getTrends(jobId, interval = "weekly") {
  // Simulates GET /api/v1/analytics/trends?job_id={jobId}&interval={interval}
  return mockGetTrends(jobId, interval);
}

/**
 * Fetch the list of extracted themes / complaint categories.
 * @param {string} jobId
 * @returns {Promise<Array>}
 */
export async function getThemes(jobId) {
  // Simulates GET /api/v1/themes?job_id={jobId}
  return mockGetThemes(jobId);
}

/**
 * Fetch verbatim quotes for a specific theme.
 * @param {string} themeId
 * @param {string} jobId
 * @param {number} page
 * @param {number} limit
 * @returns {Promise<object>}
 */
export async function getVerbatims(themeId, jobId, page = 1, limit = 20) {
  // Simulates GET /api/v1/themes/{themeId}/verbatims?job_id={jobId}&page={page}&limit={limit}
  return mockGetVerbatims(themeId, jobId, page, limit);
}

/**
 * Fetch enterprise governance and quality metrics.
 * @param {string} jobId
 * @returns {Promise<object>}
 */
export async function getGovernanceMetrics(jobId) {
  // Simulates GET /api/v1/governance/metrics?job_id={jobId}
  return mockGetGovernanceMetrics(jobId);
}
