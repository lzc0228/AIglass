/**
 * Confirm all scene descriptions API.
 * POST /api/scenes/confirm-all-descriptions - Confirm all scene descriptions for a project
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { confirmAllDescriptions, SceneError } from "@/lib/db/scenes";
import { isProjectOwner } from "@/lib/db/projects";

/**
 * POST /api/scenes/confirm-all-descriptions
 * Confirm all scene descriptions for a project
 * Body: { projectId: string }
 */
export async function POST(request: Request) {
  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await request.json();
    const { projectId } = body;

    if (!projectId) {
      return NextResponse.json(
        { error: "projectId is required" },
        { status: 400 }
      );
    }

    // Verify user owns the project
    const isOwner = await isProjectOwner(projectId, user.id);
    if (!isOwner) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 403 });
    }

    // Confirm all descriptions
    const count = await confirmAllDescriptions(projectId);

    return NextResponse.json({ count });
  } catch (error) {
    if (error instanceof SceneError) {
      if (error.code === "not_found") {
        return NextResponse.json({ error: "Project not found" }, { status: 404 });
      }
    }
    console.error("Error confirming all descriptions:", error);
    return NextResponse.json(
      { error: "Failed to confirm all descriptions" },
      { status: 500 }
    );
  }
}
