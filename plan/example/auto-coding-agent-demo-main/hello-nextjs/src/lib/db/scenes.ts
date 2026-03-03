/**
 * Scene data access layer.
 * Handles CRUD and confirmation operations for scenes.
 */

import { createClient } from "@/lib/supabase/server";
import type {
  Scene,
  SceneInsert,
  SceneUpdate,
  SceneWithMedia,
} from "@/types/database";

/**
 * Custom error class for scene operations
 */
export class SceneError extends Error {
  constructor(
    message: string,
    public code: "not_found" | "unauthorized" | "database_error"
  ) {
    super(message);
    this.name = "SceneError";
  }
}

/**
 * Create multiple scenes for a project in batch
 * @param projectId - The project ID
 * @param scenes - Array of scene data (order_index and description)
 * @returns Array of created scenes
 */
export async function createScenes(
  projectId: string,
  scenes: Array<{
    order_index: number;
    description: string;
  }>
): Promise<Scene[]> {
  const supabase = await createClient();

  const sceneData: SceneInsert[] = scenes.map((scene) => ({
    project_id: projectId,
    order_index: scene.order_index,
    description: scene.description,
    description_confirmed: false,
    image_status: "pending",
    image_confirmed: false,
    video_status: "pending",
    video_confirmed: false,
  }));

  const { data, error } = await supabase
    .from("scenes")
    .insert(sceneData)
    .select();

  if (error) {
    console.error("Error creating scenes:", error);
    throw new SceneError("Failed to create scenes", "database_error");
  }

  return data ?? [];
}

/**
 * Get all scenes for a project
 * @param projectId - The project ID
 * @returns Array of scenes
 */
export async function getScenesByProjectId(projectId: string): Promise<Scene[]> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .select("*")
    .eq("project_id", projectId)
    .order("order_index", { ascending: true });

  if (error) {
    console.error("Error fetching scenes:", error);
    throw new SceneError("Failed to fetch scenes", "database_error");
  }

  return data ?? [];
}

/**
 * Get all scenes for a project with their media
 * @param projectId - The project ID
 * @returns Array of scenes with images and videos
 */
export async function getScenesWithMediaByProjectId(
  projectId: string
): Promise<SceneWithMedia[]> {
  const supabase = await createClient();

  // Get scenes
  const { data: scenes, error: scenesError } = await supabase
    .from("scenes")
    .select("*")
    .eq("project_id", projectId)
    .order("order_index", { ascending: true });

  if (scenesError) {
    console.error("Error fetching scenes:", scenesError);
    throw new SceneError("Failed to fetch scenes", "database_error");
  }

  if (!scenes || scenes.length === 0) {
    return [];
  }

  // Get images and videos for all scenes
  const sceneIds = scenes.map((s) => s.id);

  const [imagesResult, videosResult] = await Promise.all([
    supabase.from("images").select("*").in("scene_id", sceneIds),
    supabase.from("videos").select("*").in("scene_id", sceneIds),
  ]);

  if (imagesResult.error) {
    console.error("Error fetching images:", imagesResult.error);
    throw new SceneError("Failed to fetch scene images", "database_error");
  }

  if (videosResult.error) {
    console.error("Error fetching videos:", videosResult.error);
    throw new SceneError("Failed to fetch scene videos", "database_error");
  }

  // Combine scenes with their media
  return scenes.map((scene) => ({
    ...scene,
    images: (imagesResult.data ?? []).filter((img) => img.scene_id === scene.id),
    videos: (videosResult.data ?? []).filter((vid) => vid.scene_id === scene.id),
  }));
}

/**
 * Get a single scene by ID
 * @param sceneId - The scene ID
 * @returns The scene
 */
export async function getSceneById(sceneId: string): Promise<Scene> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .select("*")
    .eq("id", sceneId)
    .single();

  if (error) {
    if (error.code === "PGRST116") {
      throw new SceneError("Scene not found", "not_found");
    }
    console.error("Error fetching scene:", error);
    throw new SceneError("Failed to fetch scene", "database_error");
  }

  return data;
}

/**
 * Update a scene's description
 * @param sceneId - The scene ID
 * @param description - The new description
 * @returns The updated scene
 */
export async function updateSceneDescription(
  sceneId: string,
  description: string
): Promise<Scene> {
  const supabase = await createClient();

  const updateData: SceneUpdate = {
    description,
  };

  const { data, error } = await supabase
    .from("scenes")
    .update(updateData)
    .eq("id", sceneId)
    .select()
    .single();

  if (error) {
    console.error("Error updating scene description:", error);
    throw new SceneError("Failed to update scene description", "database_error");
  }

  return data;
}

/**
 * Confirm a scene's description
 * @param sceneId - The scene ID
 * @returns The updated scene
 */
export async function confirmSceneDescription(
  sceneId: string
): Promise<Scene> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .update({ description_confirmed: true })
    .eq("id", sceneId)
    .select()
    .single();

  if (error) {
    console.error("Error confirming scene description:", error);
    throw new SceneError("Failed to confirm scene description", "database_error");
  }

  return data;
}

/**
 * Confirm all scene descriptions for a project
 * @param projectId - The project ID
 * @returns Number of scenes updated
 */
export async function confirmAllDescriptions(
  projectId: string
): Promise<number> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .update({ description_confirmed: true })
    .eq("project_id", projectId)
    .select();

  if (error) {
    console.error("Error confirming all descriptions:", error);
    throw new SceneError("Failed to confirm all descriptions", "database_error");
  }

  // Update project stage to 'images' after all descriptions confirmed
  await supabase
    .from("projects")
    .update({ stage: "images" })
    .eq("id", projectId);

  return data?.length ?? 0;
}

/**
 * Update a scene's image status
 * @param sceneId - The scene ID
 * @param status - The new image status
 * @returns The updated scene
 */
export async function updateSceneImageStatus(
  sceneId: string,
  status: "pending" | "processing" | "completed" | "failed"
): Promise<Scene> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .update({ image_status: status })
    .eq("id", sceneId)
    .select()
    .single();

  if (error) {
    console.error("Error updating scene image status:", error);
    throw new SceneError("Failed to update scene image status", "database_error");
  }

  return data;
}

/**
 * Confirm a scene's image
 * @param sceneId - The scene ID
 * @returns The updated scene
 */
export async function confirmSceneImage(sceneId: string): Promise<Scene> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .update({ image_confirmed: true })
    .eq("id", sceneId)
    .select()
    .single();

  if (error) {
    console.error("Error confirming scene image:", error);
    throw new SceneError("Failed to confirm scene image", "database_error");
  }

  return data;
}

/**
 * Confirm all scene images for a project
 * @param projectId - The project ID
 * @returns Number of scenes updated
 */
export async function confirmAllImages(projectId: string): Promise<number> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .update({ image_confirmed: true })
    .eq("project_id", projectId)
    .eq("image_status", "completed")
    .select();

  if (error) {
    console.error("Error confirming all images:", error);
    throw new SceneError("Failed to confirm all images", "database_error");
  }

  // Update project stage to 'videos' after all images confirmed
  await supabase
    .from("projects")
    .update({ stage: "videos" })
    .eq("id", projectId);

  return data?.length ?? 0;
}

/**
 * Update a scene's video status
 * @param sceneId - The scene ID
 * @param status - The new video status
 * @returns The updated scene
 */
export async function updateSceneVideoStatus(
  sceneId: string,
  status: "pending" | "processing" | "completed" | "failed"
): Promise<Scene> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .update({ video_status: status })
    .eq("id", sceneId)
    .select()
    .single();

  if (error) {
    console.error("Error updating scene video status:", error);
    throw new SceneError("Failed to update scene video status", "database_error");
  }

  return data;
}

/**
 * Confirm a scene's video
 * @param sceneId - The scene ID
 * @returns The updated scene
 */
export async function confirmSceneVideo(sceneId: string): Promise<Scene> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .update({ video_confirmed: true })
    .eq("id", sceneId)
    .select()
    .single();

  if (error) {
    console.error("Error confirming scene video:", error);
    throw new SceneError("Failed to confirm scene video", "database_error");
  }

  return data;
}

/**
 * Confirm all scene videos for a project
 * @param projectId - The project ID
 * @returns Number of scenes updated
 */
export async function confirmAllVideos(projectId: string): Promise<number> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .update({ video_confirmed: true })
    .eq("project_id", projectId)
    .eq("video_status", "completed")
    .select();

  if (error) {
    console.error("Error confirming all videos:", error);
    throw new SceneError("Failed to confirm all videos", "database_error");
  }

  // Update project stage to 'completed' after all videos confirmed
  await supabase
    .from("projects")
    .update({ stage: "completed" })
    .eq("id", projectId);

  return data?.length ?? 0;
}

/**
 * Delete all scenes for a project (used when regenerating scenes)
 * @param projectId - The project ID
 * @returns Number of scenes deleted
 */
export async function deleteScenesByProjectId(
  projectId: string
): Promise<number> {
  const supabase = await createClient();

  // First count scenes to return
  const { count } = await supabase
    .from("scenes")
    .select("*", { count: "exact", head: true })
    .eq("project_id", projectId);

  // Delete scenes (cascade will handle images and videos)
  const { error } = await supabase
    .from("scenes")
    .delete()
    .eq("project_id", projectId);

  if (error) {
    console.error("Error deleting scenes:", error);
    throw new SceneError("Failed to delete scenes", "database_error");
  }

  return count ?? 0;
}

/**
 * Reset scene image status (for regeneration)
 * @param sceneId - The scene ID
 * @returns The updated scene
 */
export async function resetSceneImageStatus(sceneId: string): Promise<Scene> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .update({
      image_status: "pending",
      image_confirmed: false,
    })
    .eq("id", sceneId)
    .select()
    .single();

  if (error) {
    console.error("Error resetting scene image status:", error);
    throw new SceneError("Failed to reset scene image status", "database_error");
  }

  return data;
}

/**
 * Reset scene video status (for regeneration)
 * @param sceneId - The scene ID
 * @returns The updated scene
 */
export async function resetSceneVideoStatus(sceneId: string): Promise<Scene> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("scenes")
    .update({
      video_status: "pending",
      video_confirmed: false,
    })
    .eq("id", sceneId)
    .select()
    .single();

  if (error) {
    console.error("Error resetting scene video status:", error);
    throw new SceneError("Failed to reset scene video status", "database_error");
  }

  return data;
}

/**
 * Get count of scenes with confirmed descriptions for a project
 * @param projectId - The project ID
 * @returns Count of confirmed description scenes
 */
export async function getConfirmedDescriptionCount(
  projectId: string
): Promise<number> {
  const supabase = await createClient();

  const { count, error } = await supabase
    .from("scenes")
    .select("*", { count: "exact", head: true })
    .eq("project_id", projectId)
    .eq("description_confirmed", true);

  if (error) {
    console.error("Error counting confirmed descriptions:", error);
    throw new SceneError("Failed to count confirmed descriptions", "database_error");
  }

  return count ?? 0;
}

/**
 * Get count of scenes with completed images for a project
 * @param projectId - The project ID
 * @returns Count of completed image scenes
 */
export async function getCompletedImageCount(
  projectId: string
): Promise<number> {
  const supabase = await createClient();

  const { count, error } = await supabase
    .from("scenes")
    .select("*", { count: "exact", head: true })
    .eq("project_id", projectId)
    .eq("image_status", "completed");

  if (error) {
    console.error("Error counting completed images:", error);
    throw new SceneError("Failed to count completed images", "database_error");
  }

  return count ?? 0;
}

/**
 * Get count of scenes with completed videos for a project
 * @param projectId - The project ID
 * @returns Count of completed video scenes
 */
export async function getCompletedVideoCount(
  projectId: string
): Promise<number> {
  const supabase = await createClient();

  const { count, error } = await supabase
    .from("scenes")
    .select("*", { count: "exact", head: true })
    .eq("project_id", projectId)
    .eq("video_status", "completed");

  if (error) {
    console.error("Error counting completed videos:", error);
    throw new SceneError("Failed to count completed videos", "database_error");
  }

  return count ?? 0;
}
