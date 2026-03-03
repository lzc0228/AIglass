import { createBrowserClient } from "@supabase/ssr";

import type { Database } from "@/types/database";

/**
 * Creates a Supabase client for browser-side usage.
 * This should be used in Client Components.
 *
 * @returns Supabase client configured for browser-side usage
 *
 * @example
 * // In a Client Component
 * "use client";
 *
 * import { createClient } from "@/lib/supabase/client";
 *
 * export default function MyComponent() {
 *   const supabase = createClient();
 *
 *   const handleSignOut = async () => {
 *     await supabase.auth.signOut();
 *   };
 *
 *   return <button onClick={handleSignOut}>Sign Out</button>;
 * }
 */
export function createClient() {
  return createBrowserClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
