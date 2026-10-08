const envBase = import.meta.env.VITE_API_BASE_URL;
const API_BASE =
  typeof envBase === "string" && envBase.trim()
    ? envBase.trim().replace(/\/$/, "")
    : "/api/v1";

const USER_FACING_STATUSES = new Set([400, 401, 409, 413, 422, 429, 503]);

export class ApiError extends Error {
  /**
   * @param {{ status: number, code?: string, userMessage: string }} params
   */
  constructor({ status, code, userMessage }) {
    super(userMessage);
    this.name = "ApiError";
    this.status = status;
    this.code = code ?? null;
    this.userMessage = userMessage;
  }
}

function userMessageFromBody(status, body) {
  const code = body?.code;
  const backendMessage =
    typeof body?.error === "string" && body.error.trim() ? body.error.trim() : null;

  if (status === 404 && code === "JOB_NOT_FOUND") {
    return "This analysis is no longer available. Please upload the file again.";
  }
  if (USER_FACING_STATUSES.has(status) && backendMessage) {
    return backendMessage;
  }
  if (status >= 500) {
    return backendMessage || "Something went wrong on the server. Please try again.";
  }
  return backendMessage || "Something went wrong on the server. Please try again.";
}

async function readErrorBody(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function networkError() {
  return new ApiError({
    status: 0,
    code: "NETWORK_ERROR",
    userMessage: "Cannot reach the server. Make sure the backend is running.",
  });
}

/**
 * @param {string} path
 * @param {RequestInit} [options]
 */
export async function request(path, options = {}) {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw networkError();
  }

  if (!response.ok) {
    const body = await readErrorBody(response);
    throw new ApiError({
      status: response.status,
      code: body?.code,
      userMessage: userMessageFromBody(response.status, body),
    });
  }

  return response;
}

/**
 * @param {string} path
 * @param {RequestInit} [options]
 */
export async function requestJson(path, options = {}) {
  const response = await request(path, options);
  if (response.status === 204) return null;
  return response.json();
}

/**
 * @param {string} path
 * @param {RequestInit} [options]
 */
export async function requestBlob(path, options = {}) {
  const response = await request(path, options);
  return response.blob();
}

export { API_BASE };
