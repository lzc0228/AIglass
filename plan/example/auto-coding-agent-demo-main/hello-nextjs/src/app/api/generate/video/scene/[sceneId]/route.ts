/**
 * Single scene video generation API.
 * POST /api/generate/video/scene/[sceneId] - Create video task for a single scene
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getSceneById, updateSceneVideoStatus } from "@/lib/db/scenes";
import { getProjectById } from "@/lib/db/projects";
import { getLatestImageBySceneId, createProcessingVideo, getSignedUrl } from "@/lib/db/media";
import {
  createVideoTask,
  isVolcVideoConfigured,
  VolcVideoApiError,
} from "@/lib/ai/volc-video";

interface RouteParams {
  params: Promise<{ sceneId: string }>;
}

/**
 * POST /api/generate/video/scene/[sceneId] - Create video task for a single scene
 * Body: { projectId: string }
 * Returns: { success: boolean, taskId: string, videoId: string, scene: Scene }
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

    // Check if Volc Video API is configured
    if (!isVolcVideoConfigured()) {
      return NextResponse.json(
        { error: "Video generation service is not configured. Please set VOLC_API_KEY." },
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
    await getProjectById(projectId, user.id);

    // Get the scene
    const scene = await getSceneById(sceneId);

    // Verify scene belongs to the project
    if (scene.project_id !== projectId) {
      return NextResponse.json(
        { error: "Scene does not belong to this project" },
        { status: 400 }
      );
    }

    // Check if scene image is completed
    if (scene.image_status !== "completed") {
      return NextResponse.json(
        { error: "Scene image must be completed before generating video" },
        { status: 400 }
      );
    }

    // Get the latest image for this scene
    const latestImage = await getLatestImageBySceneId(sceneId);

    if (!latestImage) {
      return NextResponse.json(
        { error: "No image found for this scene. Please generate an image first." },
        { status: 400 }
      );
    }

    // Generate a fresh signed URL for the image (valid for 1 hour)
    // This ensures the video API can access the image even from private bucket
    const imageUrl = await getSignedUrl(latestImage.storage_path, 3600);

    // Update scene video status to processing
    await updateSceneVideoStatus(sceneId, "processing");

    try {
      // Create video task using Volc API
      const task = await createVideoTask(
        imageUrl,
        scene.description,
        {
          duration: 5,
          watermark: false,
        }
      );

      // Create a video record in the database with task_id
      // This allows frontend to find the task_id even after page refresh
      const video = await createProcessingVideo(sceneId, task.taskId);

      return NextResponse.json({
        success: true,
        taskId: task.taskId,
        videoId: video.id,
        sceneId,
        status: task.status,
        message: "Video task created successfully",
      });
    } catch (generationError) {
      // Update scene video status to failed
      await updateSceneVideoStatus(sceneId, "failed");
      throw generationError;
    }
  } catch (error) {
    console.error("Error creating video task:", error);

    // Handle specific errors
    if (error instanceof VolcVideoApiError) {
      return NextResponse.json(
        { error: `Video generation error: ${error.message}` },
        { status: 502 }
      );
    }

    // Handle project/scene not found errors
    if (error instanceof Error && error.message.includes("not found")) {
      return NextResponse.json({ error: error.message }, { status: 404 });
    }

    return NextResponse.json(
      { error: "Failed to create video task" },
      { status: 500 }
    );
  }
}
