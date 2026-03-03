import { NextRequest, NextResponse } from "next/server";
import { getSignedUrls } from "@/lib/db/media";
import { createClient } from "@/lib/supabase/server";

/**
 * POST /api/storage/signed-urls
 * Generate signed URLs for multiple storage paths
 *
 * Request body:
 * - paths: string[] - Array of storage paths
 * - expiresIn?: number - URL expiration time in seconds (default: 3600)
 */
export async function POST(request: NextRequest) {
  try {
    // Check authentication
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await request.json();
    const { paths, expiresIn } = body;

    if (!paths || !Array.isArray(paths) || paths.length === 0) {
      return NextResponse.json(
        { error: "paths array is required" },
        { status: 400 }
      );
    }

    // Validate paths belong to this user (security check)
    const userId = user.id;
    const validPaths = paths.filter((path: string) => {
      // Path format: {userId}/{projectId}/{fileName}
      return path.startsWith(`${userId}/`);
    });

    if (validPaths.length === 0) {
      return NextResponse.json({ urls: {} });
    }

    // Generate signed URLs
    const urlMap = await getSignedUrls(validPaths, expiresIn ?? 3600);

    // Convert Map to object for JSON response
    const urls: Record<string, string> = {};
    urlMap.forEach((url, path) => {
      urls[path] = url;
    });

    return NextResponse.json({ urls });
  } catch (error) {
    console.error("Error generating signed URLs:", error);
    return NextResponse.json(
      { error: "Failed to generate signed URLs" },
      { status: 500 }
    );
  }
}
