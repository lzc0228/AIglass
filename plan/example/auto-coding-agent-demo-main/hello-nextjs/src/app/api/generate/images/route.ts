/**
 * Batch image generation API.
 * POST /api/generate/images - Generate images for all scenes in a project
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getScenesByProjectId, updateSceneImageStatus } from "@/lib/db/scenes";
import { getProjectById, updateProjectStage } from "@/lib/db/projects";
import {
  generateImage,
  isVolcImageConfigured,
  VolcImageApiError,
} from "@/lib/ai/volc-image";
import {
  uploadAndCreateImage,
  deleteOldSceneImages,
} from "@/lib/db/media";
import type { Image } from "@/types/database";

interface GenerationResult {
  sceneId: string;
  orderIndex: number;
  success: boolean;
  image?: Image;
  error?: string;
}

/**
 * Generate image for a single scene (internal function)
 */
async function generateSceneImage(
  userId: string,
  projectId: string,
  sceneId: string,
  orderIndex: number,
  description: string,
  style?: string
): Promise<GenerationResult> {
  try {
    // Update scene image status to processing
    await updateSceneImageStatus(sceneId, "processing");

    // Generate image using Volc API
    const imageBase64 = await generateImage(description, style, {
      size: "2K",
    });

    // Delete old images from storage and database
    await deleteOldSceneImages(sceneId);

    // Generate filename
    const timestamp = Date.now();
    const fileName = `scene-${orderIndex}-${timestamp}.png`;

    // Upload to Supabase Storage and create database record
    const image = await uploadAndCreateImage(
      userId,
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
    await updateSceneImageStatus(sceneId, "completed");

    return {
      sceneId,
      orderIndex,
      success: true,
      image,
    };
  } catch (error) {
    // Update scene image status to failed
    await updateSceneImageStatus(sceneId, "failed");

    return {
      sceneId,
      orderIndex,
      success: false,
      error: error instanceof Error ? error.message : "Unknown error",
    };
  }
}

/**
 * POST /api/generate/images - Generate images for all scenes in a project
 * Body: { projectId: string }
 * Returns: { success: boolean, results: GenerationResult[], completed: number, failed: number }
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

    // Check if Volc Image API is configured
    if (!isVolcImageConfigured()) {
      return NextResponse.json(
        { error: "Image generation service is not configured. Please set VOLC_ACCESS_KEY and VOLC_SECRET_KEY." },
        { status: 503 }
      );
    }

    const body = await request.json();
    const { projectId } = body;

    if (!projectId || typeof projectId !== "string") {
      return NextResponse.json(
        { error: "Project ID is required" },
        { status: 400 }
      );
    }

    // Verify project ownership
    const project = await getProjectById(projectId, user.id);

    // Get all scenes for the project
    const scenes = await getScenesByProjectId(projectId);

    // Filter scenes that need image generation:
    // - description_confirmed = true
    // - image_status = pending or failed
    const scenesToGenerate = scenes.filter(
      (scene) =>
        scene.description_confirmed &&
        (scene.image_status === "pending" || scene.image_status === "failed")
    );

    if (scenesToGenerate.length === 0) {
      return NextResponse.json({
        success: true,
        message: "No scenes require image generation. All scenes either have images or descriptions are not confirmed.",
        results: [],
        completed: 0,
        failed: 0,
      });
    }

    // Update project stage to 'images' if not already
    if (project.stage === "scenes") {
      await updateProjectStage(projectId, user.id, "images");
    }

    // Generate images for all scenes sequentially
    // (Could be parallelized later with rate limiting considerations)
    const results: GenerationResult[] = [];

    for (const scene of scenesToGenerate) {
      const result = await generateSceneImage(
        user.id,
        projectId,
        scene.id,
        scene.order_index,
        scene.description,
        project.style ?? undefined
      );
      results.push(result);
    }

    // Count successes and failures
    const completed = results.filter((r) => r.success).length;
    const failed = results.filter((r) => !r.success).length;

    return NextResponse.json({
      success: true,
      message: `Generated images for ${completed} scenes. ${failed} failed.`,
      results,
      completed,
      failed,
      total: scenesToGenerate.length,
    });
  } catch (error) {
    console.error("Error generating images:", error);

    // Handle specific errors
    if (error instanceof VolcImageApiError) {
      return NextResponse.json(
        { error: `Image generation error: ${error.message}` },
        { status: 502 }
      );
    }

    // Handle project not found error
    if (error instanceof Error && error.message.includes("not found")) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    return NextResponse.json(
      { error: "Failed to generate images" },
      { status: 500 }
    );
  }
}
