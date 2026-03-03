/**
 * Scene image confirmation API.
 * POST /api/scenes/:id/confirm-image - Confirm a scene's image
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import {
  getSceneById,
  confirmSceneImage,
  SceneError,
} from "@/lib/db/scenes";
import { isProjectOwner } from "@/lib/db/projects";

interface RouteParams {
  params: Promise<{ id: string }>;
}

/**
 * POST /api/scenes/:id/confirm-image
 * Confirm a scene's image
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

    // Get the scene to verify ownership and check image status
    const scene = await getSceneById(id);

    // Verify user owns the project
    const isOwner = await isProjectOwner(scene.project_id, user.id);
    if (!isOwner) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 403 });
    }

    // Check if image is completed
    if (scene.image_status !== "completed") {
      return NextResponse.json(
        { error: "Image must be completed before confirming" },
        { status: 400 }
      );
    }

    // Confirm the image
    const updatedScene = await confirmSceneImage(id);

    return NextResponse.json({ scene: updatedScene });
  } catch (error) {
    if (error instanceof SceneError) {
      if (error.code === "not_found") {
        return NextResponse.json({ error: "Scene not found" }, { status: 404 });
      }
    }
    console.error("Error confirming scene image:", error);
    return NextResponse.json(
      { error: "Failed to confirm scene image" },
      { status: 500 }
    );
  }
}
