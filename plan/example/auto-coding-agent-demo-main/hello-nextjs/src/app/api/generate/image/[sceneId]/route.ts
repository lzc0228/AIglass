/**
 * Single scene image generation API.
 * POST /api/generate/image/[sceneId] - Generate image for a single scene
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getSceneById, updateSceneImageStatus } from "@/lib/db/scenes";
import { getProjectById } from "@/lib/db/projects";
import {
  generateImage,
  isVolcImageConfigured,
  VolcImageApiError,
} from "@/lib/ai/volc-image";
import {
  uploadAndCreateImage,
  deleteOldSceneImages,
} from "@/lib/db/media";

interface RouteParams {
  params: Promise<{ sceneId: string }>;
}

/**
 * POST /api/generate/image/[sceneId] - Generate image for a single scene
 * Body: { projectId: string }
 * Returns: { success: boolean, image: Image, scene: Scene }
 */
export async function POST(request: Request, { params }: RouteParams) {
  try {
    const { sceneId } = await params;
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // Check if Volc Image API is configured
    if (!isVolcImageConfigured()) {
      return NextResponse.json(
        { error: "Image generation service is not configured. Please set VOLC_ACCESS_KEY and VOLC_SECRET_KEY." },
        { status: 503 }
      );
    }

    // Get request body for projectId
    const body = await request.json().catch(() => ({}));
    const { projectId } = body;

    if (!projectId || typeof projectId !== "string") {
      return NextResponse.json(
        { error: "Project ID is required" },
        { status: 400 }
      );
    }

    // Verify project ownership
    const project = await getProjectById(projectId, user.id);

    // Get the scene
    const scene = await getSceneById(sceneId);

    // Verify scene belongs to the project
    if (scene.project_id !== projectId) {
      return NextResponse.json(
        { error: "Scene does not belong to this project" },
        { status: 400 }
      );
    }

    // Check if scene description is confirmed
    if (!scene.description_confirmed) {
      return NextResponse.json(
        { error: "Scene description must be confirmed before generating image" },
        { status: 400 }
      );
    }

    // Update scene image status to processing
    await updateSceneImageStatus(sceneId, "processing");

    try {
      // Generate image using Volc API
      const imageBase64 = await generateImage(
        scene.description,
        project.style ?? undefined,
        {
          size: "2K",
        }
      );

      // Delete old images from storage and database
      await deleteOldSceneImages(sceneId);

      // Generate filename
      const timestamp = Date.now();
      const fileName = `scene-${scene.order_index}-${timestamp}.png`;

      // Upload to Supabase Storage and create database record
      const image = await uploadAndCreateImage(
        user.id,
        projectId,
        sceneId,
        fileName,
        imageBase64,
        {
          width: 1024,
          height: 1024,
          contentType: "image/png",
        }
      );

      // Update scene image status to completed
      const updatedScene = await updateSceneImageStatus(sceneId, "completed");

      return NextResponse.json({
        success: true,
        image,
        scene: updatedScene,
        message: "Image generated successfully",
      });
    } catch (generationError) {
      // Update scene image status to failed
      await updateSceneImageStatus(sceneId, "failed");
      throw generationError;
    }
  } catch (error) {
    console.error("Error generating image:", error);

    // Handle specific errors
    if (error instanceof VolcImageApiError) {
      return NextResponse.json(
        { error: `Image generation error: ${error.message}` },
        { status: 502 }
      );
    }

    // Handle project/scene not found errors
    if (error instanceof Error && error.message.includes("not found")) {
      return NextResponse.json({ error: error.message }, { status: 404 });
    }

    return NextResponse.json(
      { error: "Failed to generate image" },
      { status: 500 }
    );
  }
}
