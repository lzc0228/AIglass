import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { updateSceneDescription } from "@/lib/db/scenes";

interface Params {
  params: Promise<{
    id: string;
  }>;
}

/**
 * PATCH /api/scenes/:id
 * Update a scene's description
 */
export async function PATCH(request: Request, { params }: Params) {
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
    const { description } = body;

    if (!description || typeof description !== "string") {
      return NextResponse.json(
        { error: "Description is required" },
        { status: 400 }
      );
    }

    // Verify user owns the scene's project
    const { data: scene, error: sceneError } = await supabase
      .from("scenes")
      .select("id, project_id, projects!inner(user_id)")
      .eq("id", id)
      .single();

    if (sceneError || !scene) {
      return NextResponse.json({ error: "Scene not found" }, { status: 404 });
    }

    const projectData = scene.projects as { user_id: string };
    if (projectData.user_id !== user.id) {
      return NextResponse.json({ error: "Forbidden" }, { status: 403 });
    }

    // Update the scene description
    const updatedScene = await updateSceneDescription(id, description);

    return NextResponse.json({ scene: updatedScene });
  } catch (error) {
    console.error("Update scene error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
