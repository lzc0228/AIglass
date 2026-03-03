import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

/**
 * Creates a Supabase client for middleware usage and handles session refresh.
 * This should be used in the root middleware.ts file.
 *
 * @param request - The incoming Next.js request
 * @returns Object containing the response and supabase client
 *
 * @example
 * // In middleware.ts
 * import { createClient } from "@/lib/supabase/middleware";
 *
 * export async function middleware(request: NextRequest) {
 *   const { supabase, response } = await createClient(request);
 *
 *   // Refresh session if expired
 *   const { data: { session } } = await supabase.auth.getSession();
 *
 *   return response;
 * }
 */
export async function createClient(request: NextRequest) {
  let supabaseResponse = NextResponse.next({
    request,
  });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value),
          );
          supabaseResponse = NextResponse.next({
            request,
          });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  return {
    supabase,
    response: supabaseResponse,
  };
}
