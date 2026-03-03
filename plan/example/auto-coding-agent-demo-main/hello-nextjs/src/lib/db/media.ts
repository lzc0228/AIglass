/**
 * Media data access layer.
 * Handles CRUD and storage operations for images and videos.
 */

import { createClient } from "@/lib/supabase/server";
import type {
  Image,
  ImageInsert,
  Video,
  VideoInsert,
} from "@/types/database";

// Storage bucket name
const MEDIA_BUCKET = "project-media";

/**
 * Custom error class for media operations
 */
export class MediaError extends Error {
  constructor(
    message: string,
    public code: "not_found" | "unauthorized" | "storage_error" | "database_error"
  ) {
    super(message);
    this.name = "MediaError";
  }
}

// ============================================
// Image Operations
// ============================================

/**
 * Create an image record (version auto-increments)
 * @param sceneId - The scene ID
 * @param storagePath - Path in storage bucket
 * @param url - Public URL of the image
 * @param options - Additional options (width, height)
 * @returns The created image
 */
export async function createImage(
  sceneId: string,
  storagePath: string,
  url: string,
  options: {
    width?: number;
    height?: number;
  } = {}
): Promise<Image> {
  const supabase = await createClient();

  // Get current max version for this scene
  const { data: existingImages } = await supabase
    .from("images")
    .select("version")
    .eq("scene_id", sceneId)
    .order("version", { ascending: false })
    .limit(1);

  const nextVersion = (existingImages?.[0]?.version ?? 0) + 1;

  const imageData: ImageInsert = {
    scene_id: sceneId,
    storage_path: storagePath,
    url,
    width: options.width ?? null,
    height: options.height ?? null,
    version: nextVersion,
  };

  const { data, error } = await supabase
    .from("images")
    .insert(imageData)
    .select()
    .single();

  if (error) {
    console.error("Error creating image:", error);
    throw new MediaError("Failed to create image", "database_error");
  }

  return data;
}

/**
 * Get all images for a scene
 * @param sceneId - The scene ID
 * @returns Array of images (ordered by version desc)
 */
export async function getImagesBySceneId(sceneId: string): Promise<Image[]> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("images")
    .select("*")
    .eq("scene_id", sceneId)
    .order("version", { ascending: false });

  if (error) {
    console.error("Error fetching images:", error);
    throw new MediaError("Failed to fetch images", "database_error");
  }

  return data ?? [];
}

/**
 * Get the latest image for a scene
 * @param sceneId - The scene ID
 * @returns The latest image or null
 */
export async function getLatestImageBySceneId(
  sceneId: string
): Promise<Image | null> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("images")
    .select("*")
    .eq("scene_id", sceneId)
    .order("version", { ascending: false })
    .limit(1)
    .single();

  if (error) {
    if (error.code === "PGRST116") {
      return null;
    }
    console.error("Error fetching latest image:", error);
    throw new MediaError("Failed to fetch latest image", "database_error");
  }

  return data;
}

/**
 * Get an image by ID
 * @param imageId - The image ID
 * @returns The image
 */
export async function getImageById(imageId: string): Promise<Image> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("images")
    .select("*")
    .eq("id", imageId)
    .single();

  if (error) {
    if (error.code === "PGRST116") {
      throw new MediaError("Image not found", "not_found");
    }
    console.error("Error fetching image:", error);
    throw new MediaError("Failed to fetch image", "database_error");
  }

  return data;
}

/**
 * Delete all images for a scene
 * @param sceneId - The scene ID
 * @returns Number of images deleted
 */
export async function deleteImagesBySceneId(sceneId: string): Promise<number> {
  const supabase = await createClient();

  // Get count first
  const { count } = await supabase
    .from("images")
    .select("*", { count: "exact", head: true })
    .eq("scene_id", sceneId);

  const { error } = await supabase
    .from("images")
    .delete()
    .eq("scene_id", sceneId);

  if (error) {
    console.error("Error deleting images:", error);
    throw new MediaError("Failed to delete images", "database_error");
  }

  return count ?? 0;
}

// ============================================
// Video Operations
// ============================================

/**
 * Create a video record
 * @param sceneId - The scene ID
 * @param storagePath - Path in storage bucket
 * @param url - Public URL of the video
 * @param options - Additional options (duration, taskId)
 * @returns The created video
 */
export async function createVideo(
  sceneId: string,
  storagePath: string,
  url: string,
  options: {
    duration?: number;
    taskId?: string;
  } = {}
): Promise<Video> {
  const supabase = await createClient();

  // Get current max version for this scene
  const { data: existingVideos } = await supabase
    .from("videos")
    .select("version")
    .eq("scene_id", sceneId)
    .order("version", { ascending: false })
    .limit(1);

  const nextVersion = (existingVideos?.[0]?.version ?? 0) + 1;

  const videoData: VideoInsert = {
    scene_id: sceneId,
    storage_path: storagePath,
    url,
    duration: options.duration ?? null,
    task_id: options.taskId ?? null,
    version: nextVersion,
  };

  const { data, error } = await supabase
    .from("videos")
    .insert(videoData)
    .select()
    .single();

  if (error) {
    console.error("Error creating video:", error);
    throw new MediaError("Failed to create video", "database_error");
  }

  return data;
}

/**
 * Update a video's task ID (for tracking generation)
 * @param videoId - The video ID
 * @param taskId - The task ID
 * @returns The updated video
 */
export async function updateVideoTaskId(
  videoId: string,
  taskId: string
): Promise<Video> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("videos")
    .update({ task_id: taskId })
    .eq("id", videoId)
    .select()
    .single();

  if (error) {
    console.error("Error updating video task ID:", error);
    throw new MediaError("Failed to update video task ID", "database_error");
  }

  return data;
}

/**
 * Create a video record in "processing" state (with task_id but no URL yet)
 * @param sceneId - The scene ID
 * @param taskId - The video generation task ID
 * @returns The created video record
 */
export async function createProcessingVideo(
  sceneId: string,
  taskId: string
): Promise<Video> {
  const supabase = await createClient();

  // Get current max version for this scene
  const { data: existingVideos } = await supabase
    .from("videos")
    .select("version")
    .eq("scene_id", sceneId)
    .order("version", { ascending: false })
    .limit(1);

  const nextVersion = (existingVideos?.[0]?.version ?? 0) + 1;

  const videoData: VideoInsert = {
    scene_id: sceneId,
    storage_path: "", // Will be updated when video is complete
    url: "", // Will be updated when video is complete
    task_id: taskId,
    version: nextVersion,
  };

  const { data, error } = await supabase
    .from("videos")
    .insert(videoData)
    .select()
    .single();

  if (error) {
    console.error("Error creating processing video:", error);
    throw new MediaError("Failed to create processing video", "database_error");
  }

  return data;
}

/**
 * Update a video record with the completed video data
 * @param videoId - The video ID
 * @param storagePath - Path in storage bucket
 * @param url - Public URL of the video
 * @param options - Additional options (duration)
 * @returns The updated video
 */
export async function updateCompletedVideo(
  videoId: string,
  storagePath: string,
  url: string,
  options: {
    duration?: number;
  } = {}
): Promise<Video> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("videos")
    .update({
      storage_path: storagePath,
      url,
      duration: options.duration ?? null,
    })
    .eq("id", videoId)
    .select()
    .single();

  if (error) {
    console.error("Error updating completed video:", error);
    throw new MediaError("Failed to update completed video", "database_error");
  }

  return data;
}

/**
 * Get the latest video for a scene (including processing ones)
 * @param sceneId - The scene ID
 * @returns The latest video or null
 */
export async function getLatestVideoBySceneIdWithTask(
  sceneId: string
): Promise<Video | null> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("videos")
    .select("*")
    .eq("scene_id", sceneId)
    .order("version", { ascending: false })
    .limit(1)
    .single();

  if (error) {
    if (error.code === "PGRST116") {
      return null;
    }
    console.error("Error fetching latest video:", error);
    throw new MediaError("Failed to fetch latest video", "database_error");
  }

  return data;
}

/**
 * Get all videos for a scene
 * @param sceneId - The scene ID
 * @returns Array of videos (ordered by version desc)
 */
export async function getVideosBySceneId(sceneId: string): Promise<Video[]> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("videos")
    .select("*")
    .eq("scene_id", sceneId)
    .order("version", { ascending: false });

  if (error) {
    console.error("Error fetching videos:", error);
    throw new MediaError("Failed to fetch videos", "database_error");
  }

  return data ?? [];
}

/**
 * Get the latest video for a scene
 * @param sceneId - The scene ID
 * @returns The latest video or null
 */
export async function getLatestVideoBySceneId(
  sceneId: string
): Promise<Video | null> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("videos")
    .select("*")
    .eq("scene_id", sceneId)
    .order("version", { ascending: false })
    .limit(1)
    .single();

  if (error) {
    if (error.code === "PGRST116") {
      return null;
    }
    console.error("Error fetching latest video:", error);
    throw new MediaError("Failed to fetch latest video", "database_error");
  }

  return data;
}

/**
 * Get a video by ID
 * @param videoId - The video ID
 * @returns The video
 */
export async function getVideoById(videoId: string): Promise<Video> {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("videos")
    .select("*")
    .eq("id", videoId)
    .single();

  if (error) {
    if (error.code === "PGRST116") {
      throw new MediaError("Video not found", "not_found");
    }
    console.error("Error fetching video:", error);
    throw new MediaError("Failed to fetch video", "database_error");
  }

  return data;
}

/**
 * Delete all videos for a scene
 * @param sceneId - The scene ID
 * @returns Number of videos deleted
 */
export async function deleteVideosBySceneId(sceneId: string): Promise<number> {
  const supabase = await createClient();

  // Get count first
  const { count } = await supabase
    .from("videos")
    .select("*", { count: "exact", head: true })
    .eq("scene_id", sceneId);

  const { error } = await supabase
    .from("videos")
    .delete()
    .eq("scene_id", sceneId);

  if (error) {
    console.error("Error deleting videos:", error);
    throw new MediaError("Failed to delete videos", "database_error");
  }

  return count ?? 0;
}

// ============================================
// Signed URL Operations (for private bucket)
// ============================================

/**
 * Generate a signed URL for a file in storage
 * @param storagePath - The storage path
 * @param expiresIn - URL expiration time in seconds (default: 1 hour)
 * @returns Signed URL
 */
export async function getSignedUrl(
  storagePath: string,
  expiresIn: number = 3600
): Promise<string> {
  const supabase = await createClient();

  const { data, error } = await supabase.storage
    .from(MEDIA_BUCKET)
    .createSignedUrl(storagePath, expiresIn);

  if (error) {
    console.error("Error creating signed URL:", error);
    throw new MediaError("Failed to create signed URL", "storage_error");
  }

  return data.signedUrl;
}

/**
 * Generate signed URLs for multiple files
 * @param storagePaths - Array of storage paths
 * @param expiresIn - URL expiration time in seconds (default: 1 hour)
 * @returns Map of storage path to signed URL
 */
export async function getSignedUrls(
  storagePaths: string[],
  expiresIn: number = 3600
): Promise<Map<string, string>> {
  const supabase = await createClient();
  const urlMap = new Map<string, string>();

  // Process in batches to avoid rate limits
  const batchSize = 10;
  for (let i = 0; i < storagePaths.length; i += batchSize) {
    const batch = storagePaths.slice(i, i + batchSize);
    const results = await Promise.all(
      batch.map(async (path) => {
        const { data, error } = await supabase.storage
          .from(MEDIA_BUCKET)
          .createSignedUrl(path, expiresIn);
        return { path, url: data?.signedUrl, error };
      })
    );

    for (const result of results) {
      if (result.url) {
        urlMap.set(result.path, result.url);
      }
    }
  }

  return urlMap;
}

// ============================================
// Storage Operations
// ============================================

/**
 * Upload a file to Supabase Storage
 * @param userId - The user ID (for folder organization)
 * @param projectId - The project ID
 * @param fileName - The file name
 * @param file - The file data (Buffer or Blob)
 * @param options - Upload options
 * @returns Storage path and signed URL (valid for 1 hour)
 */
export async function uploadFile(
  userId: string,
  projectId: string,
  fileName: string,
  file: Buffer | Blob,
  options: {
    contentType?: string;
    upsert?: boolean;
  } = {}
): Promise<{ path: string; url: string }> {
  const supabase = await createClient();

  // Construct storage path: {userId}/{projectId}/{fileName}
  const storagePath = `${userId}/${projectId}/${fileName}`;

  const { error: uploadError } = await supabase.storage
    .from(MEDIA_BUCKET)
    .upload(storagePath, file, {
      contentType: options.contentType,
      upsert: options.upsert ?? false,
    });

  if (uploadError) {
    console.error("Error uploading file:", uploadError);
    throw new MediaError("Failed to upload file", "storage_error");
  }

  // Generate signed URL (valid for 1 hour)
  const signedUrl = await getSignedUrl(storagePath);

  return {
    path: storagePath,
    url: signedUrl,
  };
}

/**
 * Upload an image to storage and create database record
 * @param userId - The user ID
 * @param projectId - The project ID
 * @param sceneId - The scene ID
 * @param fileName - The file name
 * @param imageData - The image data (Buffer or base64 string)
 * @param options - Upload options
 * @returns The created image record
 */
export async function uploadAndCreateImage(
  userId: string,
  projectId: string,
  sceneId: string,
  fileName: string,
  imageData: Buffer | string,
  options: {
    width?: number;
    height?: number;
    contentType?: string;
  } = {}
): Promise<Image> {
  // Convert base64 string to Buffer if needed
  const buffer =
    typeof imageData === "string"
      ? Buffer.from(imageData, "base64")
      : imageData;

  // Upload to storage
  const { path, url } = await uploadFile(userId, projectId, fileName, buffer, {
    contentType: options.contentType ?? "image/png",
  });

  // Create database record
  return createImage(sceneId, path, url, {
    width: options.width,
    height: options.height,
  });
}

/**
 * Upload a video to storage and create database record
 * @param userId - The user ID
 * @param projectId - The project ID
 * @param sceneId - The scene ID
 * @param fileName - The file name
 * @param videoData - The video data (Buffer or URL to download)
 * @param options - Upload options
 * @returns The created video record
 */
export async function uploadAndCreateVideo(
  userId: string,
  projectId: string,
  sceneId: string,
  fileName: string,
  videoData: Buffer,
  options: {
    duration?: number;
    taskId?: string;
    contentType?: string;
  } = {}
): Promise<Video> {
  // Upload to storage
  const { path, url } = await uploadFile(userId, projectId, fileName, videoData, {
    contentType: options.contentType ?? "video/mp4",
  });

  // Create database record
  return createVideo(sceneId, path, url, {
    duration: options.duration,
    taskId: options.taskId,
  });
}

/**
 * Delete a file from Supabase Storage
 * @param storagePath - The storage path
 */
export async function deleteFile(storagePath: string): Promise<void> {
  const supabase = await createClient();

  const { error } = await supabase.storage
    .from(MEDIA_BUCKET)
    .remove([storagePath]);

  if (error) {
    console.error("Error deleting file:", error);
    throw new MediaError("Failed to delete file", "storage_error");
  }
}

/**
 * Delete all files for a project
 * @param userId - The user ID
 * @param projectId - The project ID
 */
export async function deleteProjectFiles(
  userId: string,
  projectId: string
): Promise<void> {
  const supabase = await createClient();

  const folderPath = `${userId}/${projectId}`;

  // List all files in the folder
  const { data: files, error: listError } = await supabase.storage
    .from(MEDIA_BUCKET)
    .list(folderPath);

  if (listError) {
    console.error("Error listing files:", listError);
    throw new MediaError("Failed to list files", "storage_error");
  }

  if (!files || files.length === 0) {
    return;
  }

  // Delete all files
  const filePaths = files.map((file) => `${folderPath}/${file.name}`);

  const { error: deleteError } = await supabase.storage
    .from(MEDIA_BUCKET)
    .remove(filePaths);

  if (deleteError) {
    console.error("Error deleting files:", deleteError);
    throw new MediaError("Failed to delete files", "storage_error");
  }
}

/**
 * Delete old images when regenerating (keeps storage clean)
 * @param sceneId - The scene ID
 */
export async function deleteOldSceneImages(sceneId: string): Promise<void> {
  const supabase = await createClient();

  // Get all images for this scene
  const images = await getImagesBySceneId(sceneId);

  if (images.length === 0) {
    return;
  }

  // Delete files from storage
  const storagePaths = images.map((img) => img.storage_path);

  const { error } = await supabase.storage
    .from(MEDIA_BUCKET)
    .remove(storagePaths);

  if (error) {
    console.error("Error deleting old images from storage:", error);
    // Don't throw, continue to delete database records
  }

  // Delete database records
  await deleteImagesBySceneId(sceneId);
}

/**
 * Delete old videos when regenerating (keeps storage clean)
 * @param sceneId - The scene ID
 */
export async function deleteOldSceneVideos(sceneId: string): Promise<void> {
  const supabase = await createClient();

  // Get all videos for this scene
  const videos = await getVideosBySceneId(sceneId);

  if (videos.length === 0) {
    return;
  }

  // Delete files from storage
  const storagePaths = videos.map((vid) => vid.storage_path);

  const { error } = await supabase.storage
    .from(MEDIA_BUCKET)
    .remove(storagePaths);

  if (error) {
    console.error("Error deleting old videos from storage:", error);
    // Don't throw, continue to delete database records
  }

  // Delete database records
  await deleteVideosBySceneId(sceneId);
}

/**
 * Get media (images and videos) for a scene
 * @param sceneId - The scene ID
 * @returns Images and videos for the scene
 */
export async function getMediaBySceneId(sceneId: string): Promise<{
  images: Image[];
  videos: Video[];
}> {
  const [images, videos] = await Promise.all([
    getImagesBySceneId(sceneId),
    getVideosBySceneId(sceneId),
  ]);

  return { images, videos };
}

/**
 * Download a file from URL and upload to storage
 * @param url - The URL to download from
 * @param userId - The user ID
 * @param projectId - The project ID
 * @param fileName - The file name
 * @returns Storage path and public URL
 */
export async function downloadAndUpload(
  url: string,
  userId: string,
  projectId: string,
  fileName: string
): Promise<{ path: string; url: string }> {
  const response = await fetch(url);

  if (!response.ok) {
    throw new MediaError(`Failed to download file: ${response.status}`, "storage_error");
  }

  const buffer = Buffer.from(await response.arrayBuffer());
  const contentType = response.headers.get("content-type") ?? undefined;

  return uploadFile(userId, projectId, fileName, buffer, { contentType });
}
