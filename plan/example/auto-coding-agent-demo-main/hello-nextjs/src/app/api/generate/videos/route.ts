/**
 * Batch video generation API.
 * POST /api/generate/videos - Create video tasks for all scenes in a project
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import {
  getScenesByProjectId,
  updateSceneVideoStatus,
} from "@/lib/db/scenes";
import { getProjectById, updateProjectStage } from "@/lib/db/projects";
import { getLatestImageBySceneId, createProcessingVideo, getSignedUrl } from "@/lib/db/media";
import {
  createVideoTask,
  isVolcVideoConfigured,
  VolcVideoApiError,
} from "@/lib/ai/volc-video";

interface VideoTaskResult {
  sceneId: string;
  orderIndex: number;
  success: boolean;
  taskId?: string;
  videoId?: string;
  error?: string;
}

/**
 * Create video task for a single scene (internal function)
 */
async function createSceneVideoTask(
  sceneId: string,
  orderIndex: number,
  description: string,
  imageUrl: string
): Promise<VideoTaskResult> {
  try {
    const task = await createVideoTask(imageUrl, description, {
      duration: 5,
      watermark: false,
    });

    // Update scene video status to processing
    await updateSceneVideoStatus(sceneId, "processing");

    // Create a video record in the database with task_id
    const video = await createProcessingVideo(sceneId, task.taskId);

    return {
      sceneId,
      orderIndex,
      success: true,
      taskId: task.taskId,
      videoId: video.id,
    };
  } catch (error) {
    // Update scene video status to failed
    await updateSceneVideoStatus(sceneId, "failed");

    return {
      sceneId,
      orderIndex,
      success: false,
      error: error instanceof Error ? error.message : "Unknown error",
    };
  }
}

/**
 * POST /api/generate/videos - Create video tasks for all scenes in a project
 * Body: { projectId: string }
 * Returns: { success: boolean, results: VideoTaskResult[], created: number, failed: number }
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

    // Check if Volc Video API is configured
    if (!isVolcVideoConfigured()) {
      return NextResponse.json(
        { error: "Video generation service is not configured. Please set VOLC_API_KEY." },
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

    // Filter scenes that need video generation:
    // - image_confirmed = true or image_status = completed
    // - video_status = pending or failed
    const scenesToGenerate = scenes.filter(
      (scene) =>
        scene.image_status === "completed" &&
        (scene.video_status === "pending" || scene.video_status === "failed")
    );

    if (scenesToGenerate.length === 0) {
      return NextResponse.json({
        success: true,
        message: "No scenes require video generation. All scenes either have videos or images are not ready.",
        results: [],
        created: 0,
        failed: 0,
      });
    }

    // Update project stage to 'videos' if not already
    if (project.stage === "images") {
      await updateProjectStage(projectId, user.id, "videos");
    }

    // Create video tasks for all scenes sequentially
    const results: VideoTaskResult[] = [];

    for (const scene of scenesToGenerate) {
      // Get the latest image for this scene
      const latestImage = await getLatestImageBySceneId(scene.id);

      if (!latestImage) {
        results.push({
          sceneId: scene.id,
          orderIndex: scene.order_index,
          success: false,
          error: "No image found for scene",
        });
        continue;
      }

      // Generate a fresh signed URL for the image (valid for 1 hour)
      const imageUrl = await getSignedUrl(latestImage.storage_path, 3600);

      const result = await createSceneVideoTask(
        scene.id,
        scene.order_index,
        scene.description,
        imageUrl
      );
      results.push(result);
    }

    // Count successes and failures
    const created = results.filter((r) => r.success).length;
    const failed = results.filter((r) => !r.success).length;

    return NextResponse.json({
      success: true,
      message: `Created video tasks for ${created} scenes. ${failed} failed.`,
      results,
      created,
      failed,
      total: scenesToGenerate.length,
    });
  } catch (error) {
    console.error("Error creating video tasks:", error);

    // Handle specific errors
    if (error instanceof VolcVideoApiError) {
      return NextResponse.json(
        { error: `Video generation error: ${error.message}` },
        { status: 502 }
      );
    }

    // Handle project not found error
    if (error instanceof Error && error.message.includes("not found")) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    return NextResponse.json(
      { error: "Failed to create video tasks" },
      { status: 500 }
    );
  }
}
