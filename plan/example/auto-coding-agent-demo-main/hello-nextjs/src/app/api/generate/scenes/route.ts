/**
 * Scene generation API routes.
 * POST /api/generate/scenes - Generate scenes from a project's story
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getProjectById, updateProjectStage } from "@/lib/db/projects";
import {
  createScenes,
  deleteScenesByProjectId,
} from "@/lib/db/scenes";
import {
  storyToScenes,
  isZhipuConfigured,
  ZhipuApiError,
} from "@/lib/ai/zhipu";

/**
 * POST /api/generate/scenes - Generate scenes from a project's story
 * Body: { projectId: string }
 * Returns: { scenes: Scene[] }
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

    // Check if Zhipu AI is configured
    if (!isZhipuConfigured()) {
      return NextResponse.json(
        { error: "AI service is not configured. Please set ZHIPU_API_KEY." },
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

    // Get the project and verify ownership
    const project = await getProjectById(projectId, user.id);

    if (!project.story) {
      return NextResponse.json(
        { error: "Project has no story content. Please add a story first." },
        { status: 400 }
      );
    }

    // Generate scenes using Zhipu AI
    const sceneDescriptions = await storyToScenes(project.story, project.style ?? undefined);

    if (sceneDescriptions.length === 0) {
      return NextResponse.json(
        { error: "Failed to generate scenes. Please try again." },
        { status: 500 }
      );
    }

    // Delete existing scenes if any (for regeneration)
    await deleteScenesByProjectId(projectId);

    // Create new scenes in the database
    const newScenes = await createScenes(projectId, sceneDescriptions);

    // Update project stage to 'scenes'
    await updateProjectStage(projectId, user.id, "scenes");

    return NextResponse.json({
      success: true,
      scenes: newScenes,
      message: `Successfully generated ${newScenes.length} scenes`,
    });
  } catch (error) {
    console.error("Error generating scenes:", error);

    // Handle specific errors
    if (error instanceof ZhipuApiError) {
      return NextResponse.json(
        { error: `AI service error: ${error.message}` },
        { status: 502 }
      );
    }

    // Handle project not found error
    if (error instanceof Error && error.message.includes("not found")) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    return NextResponse.json(
      { error: "Failed to generate scenes" },
      { status: 500 }
    );
  }
}
