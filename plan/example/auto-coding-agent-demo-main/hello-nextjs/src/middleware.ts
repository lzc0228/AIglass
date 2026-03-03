import { createClient } from "@/lib/supabase/middleware";
import { type NextRequest, NextResponse } from "next/server";

/**
 * Middleware for handling Supabase session refresh and auth protection.
 *
 * Protected routes:
 * - /projects/*
 * - /create/*
 *
 * Public routes:
 * - /login
 * - /register
 * - / (home)
 * - /api/*
 */
export async function middleware(request: NextRequest) {
  const { supabase, response } = await createClient(request);

  // Refresh session if expired - required for Server Components
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const { pathname } = request.nextUrl;

  // Protected routes that require authentication
  const protectedRoutes = ["/projects", "/create"];
  const isProtectedRoute = protectedRoutes.some((route) =>
    pathname.startsWith(route),
  );

  // Auth routes that should redirect to home if already logged in
  const authRoutes = ["/login", "/register"];
  const isAuthRoute = authRoutes.some((route) => pathname.startsWith(route));

  // If trying to access protected route without session, redirect to login
  if (isProtectedRoute && !session) {
    const redirectUrl = new URL("/login", request.url);
    redirectUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(redirectUrl);
  }

  // If trying to access auth routes with session, redirect to home
  if (isAuthRoute && session) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return response;
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public folder
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
