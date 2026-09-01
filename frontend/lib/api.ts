/**
 * The single door to the API.
 *
 * Every request sends cookies (`credentials: "include"`) because the session is
 * an HTTP-only cookie the JS can never read, and every state-changing request
 * carries the double-submit CSRF token from the readable companion cookie.
 */

import type { ApiErrorBody } from "@/types/api-error";

/**
 * Where the API lives, resolved from the page's own origin so one build serves
 * every address the demo is reached on — no rebuild when the LAN IP changes:
 *
 *   https://<host>        (behind the Caddy front door) -> "", /api/* is same-origin
 *   http://<host>:3000    (next dev, or the frontend container) -> http://<host>:8000
 *
 * `NEXT_PUBLIC_API_URL` still wins when set, for a deployment whose API really
 * does live on another host. On the server the base is empty, so server-rendered
 * markup stays relative and matches what the client renders after hydration.
 */
const CONFIGURED_API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const FRONTEND_PORT = "3000";
const BACKEND_PORT = "8000";

function resolveApiUrl(): string {
  if (CONFIGURED_API_URL) return CONFIGURED_API_URL;
  if (typeof window === "undefined") return "";
  const { protocol, hostname, port } = window.location;
  return port === FRONTEND_PORT ? `${protocol}//${hostname}:${BACKEND_PORT}` : "";
}

export const API_URL = resolveApiUrl();

/**
 * Resolve a stored media URL for display.
 *
 * Uploads are stored as origin-relative paths so they load from whichever
 * address the app is opened on. A creator may also paste an absolute URL to an
 * image hosted elsewhere, which is passed through untouched.
 */
export function mediaUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  return /^(https?:)?\/\//i.test(url) || url.startsWith("data:") ? url : `${API_URL}${url}`;
}

const CSRF_COOKIE = "cw_csrf";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** True when the user simply is not signed in, which the UI treats as a state
   *  rather than an error. */
  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Absolute URL override, used only by tests. */
  baseUrl?: string;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, baseUrl, headers, ...rest } = options;
  const method = (rest.method || "GET").toUpperCase();

  const finalHeaders: Record<string, string> = {
    Accept: "application/json",
    ...((headers as Record<string, string>) || {}),
  };

  let payload: BodyInit | undefined;
  if (body !== undefined) {
    if (body instanceof FormData) {
      payload = body; // let the browser set the multipart boundary
    } else {
      finalHeaders["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }

  if (UNSAFE.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) finalHeaders["X-CSRF-Token"] = csrf;
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl ?? API_URL}${path}`, {
      ...rest,
      method,
      headers: finalHeaders,
      body: payload,
      credentials: "include",
      cache: "no-store",
    });
  } catch {
    // A network-level failure is not a server error; say so plainly.
    throw new ApiError(
      0,
      "network_error",
      "Could not reach the CrowdWise API. Check that the backend is running.",
    );
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = { error: { code: "invalid_response", message: text.slice(0, 300) } };
    }
  }

  if (!response.ok) {
    const envelope = (parsed as { error?: ApiErrorBody })?.error;
    throw new ApiError(
      response.status,
      envelope?.code || "http_error",
      envelope?.message || `Request failed with status ${response.status}.`,
      envelope?.details,
    );
  }

  return parsed as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    apiFetch<T>(path, { ...options, method: "DELETE" }),
};
