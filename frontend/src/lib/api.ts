/**
 * Axios API client — same-origin requests via Next.js proxy with httpOnly cookie auth.
 */
import axios from "axios";

/** Browser: relative URLs (Next rewrites /api → backend). SSR fallback for direct calls. */
export function apiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return "";
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

const api = axios.create({
  baseURL: apiBaseUrl(),
  headers: { "Content-Type": "application/json" },
  timeout: 120_000,
  withCredentials: true,
});

export const apiLong = axios.create({
  baseURL: apiBaseUrl(),
  headers: { "Content-Type": "application/json" },
  timeout: 180_000,
  withCredentials: true,
});

function attachAuth(client: typeof api) {
  client.interceptors.response.use(
    (res) => res,
    (err) => {
      if (err.response?.status === 401 && typeof window !== "undefined") {
        if (!window.location.pathname.startsWith("/login")) {
          window.location.href = "/login";
        }
      }
      return Promise.reject(err);
    },
  );
}

attachAuth(api);
attachAuth(apiLong);

export default api;
