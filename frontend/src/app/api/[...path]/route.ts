/**
 * BFF proxy — forwards /api/* to FastAPI and preserves Set-Cookie (required for httpOnly auth).
 * Route handlers take precedence over next.config rewrites.
 */
import { NextRequest, NextResponse } from "next/server";

/** Render API — used on Vercel when BACKEND_URL is not set in project env. */
const PRODUCTION_BACKEND_URL = "https://sumitnayak210106-planning.hf.space";

function resolveBackendUrl(): string {
  const fromEnv = process.env.BACKEND_URL?.trim() || process.env.NEXT_PUBLIC_API_URL?.trim();
  if (fromEnv) return fromEnv;
  if (process.env.VERCEL) return PRODUCTION_BACKEND_URL;
  return "http://localhost:8000";
}

const BACKEND = resolveBackendUrl();

function isLocalBackend(url: string): boolean {
  try {
    const { hostname } = new URL(url);
    return (
      hostname === "localhost" ||
      hostname === "127.0.0.1" ||
      hostname === "::1" ||
      hostname.endsWith(".local")
    );
  } catch {
    return false;
  }
}

function backendUnreachableDetail(): string {
  if (process.env.VERCEL && isLocalBackend(BACKEND)) {
    return (
      `BACKEND_URL is "${BACKEND}" but this app runs on Vercel — it cannot reach your PC's localhost. ` +
      "Expose your local API with ngrok/Cloudflare Tunnel and set BACKEND_URL on Vercel to that public HTTPS URL " +
      "(e.g. https://abc123.ngrok-free.app). Or run the frontend locally: npm run dev in frontend/."
    );
  }
  return `Cannot reach API server at ${BACKEND}. Is the backend running and reachable from the internet?`;
}

/** Rewrite Set-Cookie from upstream so auth works when Vercel (HTTPS) proxies a dev backend. */
function rewriteSetCookieHeader(cookie: string, requestIsHttps: boolean): string {
  let out = cookie.replace(/;\s*Domain=[^;]*/gi, "");
  if (requestIsHttps && !/;\s*Secure/i.test(out)) {
    out += "; Secure";
  }
  return out;
}

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
]);

/** fetch() decompresses gzip bodies but may leave Content-Encoding — breaks browsers. */
const STRIP_RESPONSE_HEADERS = new Set([
  ...HOP_BY_HOP,
  "content-encoding",
  "content-length",
]);

function forwardRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (HOP_BY_HOP.has(lower)) return;
    // Avoid upstream gzip; prevents ERR_CONTENT_DECODING_FAILED after proxy decompresses.
    if (lower === "accept-encoding") return;
    headers.set(key, value);
  });
  return headers;
}

function buildResponseHeaders(upstream: Response, requestIsHttps: boolean): Headers {
  const headers = new Headers();
  upstream.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (STRIP_RESPONSE_HEADERS.has(lower) || lower === "set-cookie") return;
    headers.append(key, value);
  });
  if (typeof upstream.headers.getSetCookie === "function") {
    for (const cookie of upstream.headers.getSetCookie()) {
      headers.append("Set-Cookie", rewriteSetCookieHeader(cookie, requestIsHttps));
    }
  } else {
    const cookie = upstream.headers.get("set-cookie");
    if (cookie) headers.append("Set-Cookie", rewriteSetCookieHeader(cookie, requestIsHttps));
  }
  return headers;
}

async function proxy(request: NextRequest, pathSegments: string[]): Promise<NextResponse> {
  const path = pathSegments.join("/");
  const search = request.nextUrl.search;
  const url = `${BACKEND}/api/${path}${search}`;
  const requestIsHttps = request.nextUrl.protocol === "https:";

  if (process.env.VERCEL && isLocalBackend(BACKEND)) {
    return NextResponse.json({ detail: backendUnreachableDetail() }, { status: 502 });
  }

  const headers = forwardRequestHeaders(request);

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
    keepalive: request.method === "GET",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  let upstream: Response;
  try {
    upstream = await fetch(url, init);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Backend unreachable";
    return NextResponse.json(
      { detail: `${backendUnreachableDetail()} ${message}` },
      { status: 502 },
    );
  }

  const body = await upstream.arrayBuffer();
  return new NextResponse(body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: buildResponseHeaders(upstream, requestIsHttps),
  });
}

type RouteCtx = { params: Promise<{ path: string[] }> };

async function handler(request: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(request, path);
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
export const OPTIONS = handler;

export const runtime = "nodejs";
export const maxDuration = 60;
