/**
 * Confirm all scene videos API.
 * POST /api/scenes/confirm-all-videos - Confirm all scene videos for a project
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { confirmAllVideos, SceneError } from "@/lib/db/scenes";
import { isProjectOwner, updateProjectStage, ProjectError } from "@/lib/db/projects";

/**
 * POST /api/scenes/confirm-all-videos
 * Confirm all scene videos for a project and mark project as completed
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

    // Confirm all videos (only those with completed status)
    const count = await confirmAllVideos(projectId);

    // Update project stage to 'completed'
    await updateProjectStage(projectId, user.id, "completed");

    return NextResponse.json({ count, stage: "completed" });
  } catch (error) {
    if (error instanceof SceneError) {
      if (error.code === "not_found") {
        return NextResponse.json({ error: "Project not found" }, { status: 404 });
      }
    }
    if (error instanceof ProjectError) {
      if (error.code === "not_found") {
        return NextResponse.json({ error: "Project not found" }, { status: 404 });
      }
      if (error.code === "unauthorized") {
        return NextResponse.json({ error: "Unauthorized" }, { status: 403 });
      }
    }
    console.error("Error confirming all videos:", error);
    return NextResponse.json(
      { error: "Failed to confirm all videos" },
      { status: 500 }
    );
  }
}
