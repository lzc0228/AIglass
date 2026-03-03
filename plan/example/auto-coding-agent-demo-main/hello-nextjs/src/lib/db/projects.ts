/**
 * Project data access layer.
 * Handles CRUD operations for projects.
 */

import { createClient } from "@/lib/supabase/server";
import type {
  Project,
  ProjectInsert,
  ProjectUpdate,
  ProjectWithScenes,
  project_stage,
} from "@/types/database";

/**
 * Custom error class for project operations
 */
export class ProjectError extends Error {
  constructor(
    message: string,
    public code: "not_found" | "unauthorized" | "database_error"
  ) {
    super(message);
    this.name = "ProjectError";
  }
}

/**
 * Create a new project
 * @param userId - The user ID who owns the project
 * @param title - Project title
 * @param story - Optional story content
 * @param style - Optional visual style
 * @returns The created project
 */
export async function createProject(
  userId: string,
  title: string,
  story?: string,
  style?: string
): Promise<Project> {
  const supabase = await createClient();

  const projectData: ProjectInsert = {
    user_id: userId,
    title,
    story: story ?? null,
    style: style ?? null,
    stage: "draft",
  };

  const { data, error } = await supabase
    .from("projects")
    .insert(projectData)
    .select()
    .single();

  if (error) {
    console.error("Error creating project:", error);
    throw new ProjectError("Failed to create project", "database_error");
  }

  return data;
}

/**
 * Get all projects for a user with pagination
 * @param userId - The user ID
 * @param options - Pagination options
 * @returns Array of projects and total count
 */
export async function getProjects(
  userId: string,
  options: {
    page?: number;
    limit?: number;
  } = {}
): Promise<{ projects: Project[]; total: number }> {
  const supabase = await createClient();
  const page = options.page ?? 1;
  const limit = options.limit ?? 20;
  const offset = (page - 1) * limit;

  // Get projects with count
  const { data, error, count } = await supabase
    .from("projects")
    .select("*", { count: "exact" })
    .eq("user_id", userId)
    .order("updated_at", { ascending: false })
    .range(offset, offset + limit - 1);

  if (error) {
    console.error("Error fetching projects:", error);
    throw new ProjectError("Failed to fetch projects", "database_error");
  }

  return {
    projects: data ?? [],
    total: count ?? 0,
  };
}

/**
 * Get a single project by ID with all scenes and media
 * @param projectId - The project ID
 * @param userId - The user ID (for authorization)
 * @returns Project with scenes and media
 */
export async function getProjectById(
  projectId: string,
  userId: string
): Promise<ProjectWithScenes> {
  const supabase = await createClient();

  // First get the project and verify ownership
  const { data: project, error: projectError } = await supabase
    .from("projects")
    .select("*")
    .eq("id", projectId)
    .eq("user_id", userId)
    .single();

  if (projectError) {
    if (projectError.code === "PGRST116") {
      throw new ProjectError("Project not found", "not_found");
    }
    console.error("Error fetching project:", projectError);
    throw new ProjectError("Failed to fetch project", "database_error");
  }

  // Get scenes for this project
  const { data: scenes, error: scenesError } = await supabase
    .from("scenes")
    .select("*")
    .eq("project_id", projectId)
    .order("order_index", { ascending: true });

  if (scenesError) {
    console.error("Error fetching scenes:", scenesError);
    throw new ProjectError("Failed to fetch project scenes", "database_error");
  }

  // Get images and videos for each scene
  const sceneIds = scenes?.map((s) => s.id) ?? [];

  const [imagesResult, videosResult] = await Promise.all([
    sceneIds.length > 0
      ? supabase.from("images").select("*").in("scene_id", sceneIds)
      : { data: [], error: null },
    sceneIds.length > 0
      ? supabase.from("videos").select("*").in("scene_id", sceneIds)
      : { data: [], error: null },
  ]);

  if (imagesResult.error) {
    console.error("Error fetching images:", imagesResult.error);
    throw new ProjectError("Failed to fetch project images", "database_error");
  }

  if (videosResult.error) {
    console.error("Error fetching videos:", videosResult.error);
    throw new ProjectError("Failed to fetch project videos", "database_error");
  }

  // Combine scenes with their media
  const scenesWithMedia = (scenes ?? []).map((scene) => ({
    ...scene,
    images: (imagesResult.data ?? []).filter((img) => img.scene_id === scene.id),
    videos: (videosResult.data ?? []).filter((vid) => vid.scene_id === scene.id),
  }));

  return {
    ...project,
    scenes: scenesWithMedia,
  };
}

/**
 * Update a project's basic info (title, story, style, stage)
 * @param projectId - The project ID
 * @param userId - The user ID (for authorization)
 * @param updates - The fields to update
 * @returns The updated project
 */
export async function updateProject(
  projectId: string,
  userId: string,
  updates: {
    title?: string;
    story?: string;
    style?: string;
    stage?: project_stage;
  }
): Promise<Project> {
  const supabase = await createClient();

  // First verify ownership
  const { data: existing, error: checkError } = await supabase
    .from("projects")
    .select("user_id")
    .eq("id", projectId)
    .single();

  if (checkError) {
    if (checkError.code === "PGRST116") {
      throw new ProjectError("Project not found", "not_found");
    }
    console.error("Error checking project:", checkError);
    throw new ProjectError("Failed to update project", "database_error");
  }

  if (existing.user_id !== userId) {
    throw new ProjectError("Unauthorized to update this project", "unauthorized");
  }

  const updateData: ProjectUpdate = {
    ...updates,
    updated_at: new Date().toISOString(),
  };

  const { data, error } = await supabase
    .from("projects")
    .update(updateData)
    .eq("id", projectId)
    .select()
    .single();

  if (error) {
    console.error("Error updating project:", error);
    throw new ProjectError("Failed to update project", "database_error");
  }

  return data;
}

/**
 * Update a project's stage
 * @param projectId - The project ID
 * @param userId - The user ID (for authorization)
 * @param stage - The new stage
 * @returns The updated project
 */
export async function updateProjectStage(
  projectId: string,
  userId: string,
  stage: project_stage
): Promise<Project> {
  const supabase = await createClient();

  // First verify ownership
  const { data: existing, error: checkError } = await supabase
    .from("projects")
    .select("user_id")
    .eq("id", projectId)
    .single();

  if (checkError) {
    if (checkError.code === "PGRST116") {
      throw new ProjectError("Project not found", "not_found");
    }
    console.error("Error checking project:", checkError);
    throw new ProjectError("Failed to update project stage", "database_error");
  }

  if (existing.user_id !== userId) {
    throw new ProjectError("Unauthorized to update this project", "unauthorized");
  }

  const { data, error } = await supabase
    .from("projects")
    .update({
      stage,
      updated_at: new Date().toISOString(),
    })
    .eq("id", projectId)
    .select()
    .single();

  if (error) {
    console.error("Error updating project stage:", error);
    throw new ProjectError("Failed to update project stage", "database_error");
  }

  return data;
}

/**
 * Delete a project and all its associated data
 * @param projectId - The project ID
 * @param userId - The user ID (for authorization)
 */
export async function deleteProject(
  projectId: string,
  userId: string
): Promise<void> {
  const supabase = await createClient();

  // First verify ownership
  const { data: existing, error: checkError } = await supabase
    .from("projects")
    .select("user_id")
    .eq("id", projectId)
    .single();

  if (checkError) {
    if (checkError.code === "PGRST116") {
      throw new ProjectError("Project not found", "not_found");
    }
    console.error("Error checking project:", checkError);
    throw new ProjectError("Failed to delete project", "database_error");
  }

  if (existing.user_id !== userId) {
    throw new ProjectError("Unauthorized to delete this project", "unauthorized");
  }

  // Delete the project (cascade will handle scenes, images, videos)
  const { error } = await supabase
    .from("projects")
    .delete()
    .eq("id", projectId);

  if (error) {
    console.error("Error deleting project:", error);
    throw new ProjectError("Failed to delete project", "database_error");
  }
}

/**
 * Check if a user owns a project
 * @param projectId - The project ID
 * @param userId - The user ID
 * @returns True if the user owns the project
 */
export async function isProjectOwner(
  projectId: string,
  userId: string
): Promise<boolean> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("projects")
    .select("user_id")
    .eq("id", projectId)
    .single();

  if (error) {
    return false;
  }

  return data.user_id === userId;
}
