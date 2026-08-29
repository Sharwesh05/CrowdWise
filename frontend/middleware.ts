import { NextResponse, type NextRequest } from "next/server";

/**
 * Route protection at the edge.
 *
 * This only checks that a session cookie is present — it deliberately does not
 * decode or trust it. Roles and permissions are enforced by the API on every
 * request; this middleware exists so a signed-out visitor gets a sign-in page
 * instead of a dashboard shell that will fail its first fetch.
 */
const PROTECTED_PREFIXES = ["/creator", "/contributor", "/admin"];
const SESSION_COOKIE = "cw_access";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (!PROTECTED_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  if (request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.next();
  }

  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = `?next=${encodeURIComponent(pathname)}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/creator/:path*", "/contributor/:path*", "/admin/:path*"],
};
