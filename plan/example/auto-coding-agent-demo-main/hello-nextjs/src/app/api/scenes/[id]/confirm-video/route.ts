/**
 * Scene video confirmation API.
 * POST /api/scenes/:id/confirm-video - Confirm a scene's video
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import {
  getSceneById,
  confirmSceneVideo,
  SceneError,
} from "@/lib/db/scenes";
import { isProjectOwner } from "@/lib/db/projects";

interface RouteParams {
  params: Promise<{ id: string }>;
}

/**
 * POST /api/scenes/:id/confirm-video
 * Confirm a scene's video
 */
export async function POST(request: Request, { params }: RouteParams) {
  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { id } = await params;

    // Get the scene to verify ownership and check video status
    const scene = await getSceneById(id);

    // Verify user owns the project
    const isOwner = await isProjectOwner(scene.project_id, user.id);
    if (!isOwner) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 403 });
    }

    // Check if video is completed
    if (scene.video_status !== "completed") {
      return NextResponse.json(
        { error: "Video must be completed before confirming" },
        { status: 400 }
      );
    }

    // Confirm the video
    const updatedScene = await confirmSceneVideo(id);

    return NextResponse.json({ scene: updatedScene });
  } catch (error) {
    if (error instanceof SceneError) {
      if (error.code === "not_found") {
        return NextResponse.json({ error: "Scene not found" }, { status: 404 });
      }
    }
    console.error("Error confirming scene video:", error);
    return NextResponse.json(
      { error: "Failed to confirm scene video" },
      { status: 500 }
    );
  }
}
