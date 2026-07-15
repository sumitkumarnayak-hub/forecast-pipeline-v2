import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Routes that don't require authentication
const publicRoutes = ["/login"];

export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;

  // Skip static files and API routes (if any are handled by Next.js)
  if (
    path.startsWith("/_next") ||
    path.startsWith("/api") ||
    path.includes(".") // e.g. favicon.ico
  ) {
    return NextResponse.next();
  }

  // Check if it's a public route
  if (publicRoutes.includes(path)) {
    return NextResponse.next();
  }

  // Check for the ps_auth cookie (set by backend on successful login)
  const token = request.cookies.get("ps_auth")?.value;

  if (!token) {
    // Redirect to login if not authenticated
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    // Optionally preserve the original URL to redirect back after login
    url.searchParams.set("callbackUrl", request.url);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico, sitemap.xml, robots.txt (metadata files)
     */
    '/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)',
  ],
};
