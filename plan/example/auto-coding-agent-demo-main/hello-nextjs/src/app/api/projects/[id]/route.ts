/**
 * Project API routes.
 * GET /api/projects/:id - Get project details
 * PATCH /api/projects/:id - Update project
 * DELETE /api/projects/:id - Delete project
 */

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import {
  getProjectById,
  updateProject,
  deleteProject,
  ProjectError,
} from "@/lib/db/projects";
import type { project_stage } from "@/types/database";

interface RouteParams {
  params: Promise<{ id: string }>;
}

/**
 * GET /api/projects/:id - Get project details with scenes and media
 */
export async function GET(request: Request, { params }: RouteParams) {
  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { id } = await params;

    const project = await getProjectById(id, user.id);

    return NextResponse.json({ project });
  } catch (error) {
    if (error instanceof ProjectError) {
      if (error.code === "not_found") {
        return NextResponse.json({ error: "Project not found" }, { status: 404 });
      }
      if (error.code === "unauthorized") {
        return NextResponse.json({ error: "Unauthorized" }, { status: 403 });
      }
    }
    console.error("Error fetching project:", error);
    return NextResponse.json(
      { error: "Failed to fetch project" },
      { status: 500 }
    );
  }
}

/**
 * PATCH /api/projects/:id - Update project (title, story, style, stage)
 * Body: { title?: string, story?: string, style?: string, stage?: string }
 */
export async function PATCH(request: Request, { params }: RouteParams) {
  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { id } = await params;
    const body = await request.json();
    const { title, story, style, stage } = body;

    // Validate at least one field is provided
    if (!title && story === undefined && style === undefined && !stage) {
      return NextResponse.json(
        { error: "At least one field is required" },
        { status: 400 }
      );
    }

    // Validate stage if provided
    if (stage) {
      const validStages = ["draft", "scenes", "images", "videos", "completed"];
      if (!validStages.includes(stage)) {
        return NextResponse.json(
          { error: "Invalid stage value" },
          { status: 400 }
        );
      }
    }

    const project = await updateProject(id, user.id, {
      title,
      story,
      style,
      stage: stage as project_stage | undefined,
    });

    return NextResponse.json({ project });
  } catch (error) {
    if (error instanceof ProjectError) {
      if (error.code === "not_found") {
        return NextResponse.json({ error: "Project not found" }, { status: 404 });
      }
      if (error.code === "unauthorized") {
        return NextResponse.json({ error: "Unauthorized" }, { status: 403 });
      }
    }
    console.error("Error updating project:", error);
    return NextResponse.json(
      { error: "Failed to update project" },
      { status: 500 }
    );
  }
}

/**
 * DELETE /api/projects/:id - Delete project
 */
export async function DELETE(request: Request, { params }: RouteParams) {
  try {
    const supabase = await createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { id } = await params;

    await deleteProject(id, user.id);

    return NextResponse.json({ success: true });
  } catch (error) {
    if (error instanceof ProjectError) {
      if (error.code === "not_found") {
        return NextResponse.json({ error: "Project not found" }, { status: 404 });
      }
      if (error.code === "unauthorized") {
        return NextResponse.json({ error: "Unauthorized" }, { status: 403 });
      }
    }
    console.error("Error deleting project:", error);
    return NextResponse.json(
      { error: "Failed to delete project" },
      { status: 500 }
    );
  }
}
