/**
 * Volcano Engine Video Generation API wrapper.
 * Handles video generation using Doubao Seedance model (image-to-video).
 * API: https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks
 */

// Configuration
const VOLC_API_KEY = process.env.VOLC_API_KEY;
const VOLC_VIDEO_TASKS_URL = process.env.VOLC_VIDEO_TASKS_URL || "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks";
const DEFAULT_MODEL = "doubao-seedance-1-5-pro-251215";

// Retry configuration
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;
const REQUEST_TIMEOUT_MS = 60000; // 1 minute for API calls

/**
 * Custom error class for Volcano Engine Video API errors
 */
export class VolcVideoApiError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public errorCode?: string
  ) {
    super(message);
    this.name = "VolcVideoApiError";
  }
}

/**
 * Video task status enum
 */
export type VideoTaskStatus = "pending" | "processing" | "completed" | "failed";

/**
 * Sleep utility for retry delays
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Check if the API credentials are configured
 */
export function isVolcVideoConfigured(): boolean {
  return !!VOLC_API_KEY;
}

/**
 * Result of video generation task creation
 */
export interface VideoTaskResult {
  taskId: string;
  status: VideoTaskStatus;
}

/**
 * Result of video task status query
 */
export interface VideoStatusResult {
  taskId: string;
  status: VideoTaskStatus;
  progress?: number;
  videoUrl?: string;
  errorMessage?: string;
}

/**
 * Create task response
 */
interface CreateTaskResponse {
  id: string;
  status?: string;
  error?: {
    message: string;
    type: string;
    code: string;
  };
}

/**
 * Get task status response
 */
interface GetTaskResponse {
  id: string;
  status: string;
  content?: {
    video_url?: string;
  };
  output?: {
    url?: string;
    duration?: number;
  };
  error?: {
    message: string;
    type: string;
    code: string;
  };
}

/**
 * Create a video generation task from an image
 * @param imageUrl - URL of the source image
 * @param prompt - Description of the desired video motion
 * @param options - Additional generation options
 * @returns Task ID and initial status
 */
export async function createVideoTask(
  imageUrl: string,
  prompt?: string,
  options: {
    duration?: number;
    watermark?: boolean;
  } = {}
): Promise<VideoTaskResult> {
  if (!isVolcVideoConfigured()) {
    throw new VolcVideoApiError("Volcano Engine video generation is not configured. Please set VOLC_API_KEY.");
  }

  // Build prompt with parameters
  const duration = options.duration ?? 5;
  const watermark = options.watermark ?? false;
  const fullPrompt = `${prompt ?? ""} --duration ${duration} --camerafixed false --watermark ${watermark}`;

  const requestBody = {
    model: DEFAULT_MODEL,
    content: [
      {
        type: "text",
        text: fullPrompt,
      },
      {
        type: "image_url",
        image_url: {
          url: imageUrl,
        },
      },
    ],
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let lastError: Error | null = null;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      const response = await fetch(VOLC_VIDEO_TASKS_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${VOLC_API_KEY}`,
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      const data: CreateTaskResponse = await response.json();

      // Check for API error
      if (data.error) {
        throw new VolcVideoApiError(
          data.error.message || `API error: ${data.error.code}`,
          response.status,
          data.error.code
        );
      }

      if (!response.ok) {
        throw new VolcVideoApiError(
          `HTTP error: ${response.status}`,
          response.status
        );
      }

      if (!data.id) {
        throw new VolcVideoApiError("No task ID in response");
      }

      clearTimeout(timeoutId);
      return {
        taskId: data.id,
        status: (data.status as VideoTaskStatus) || "pending",
      };
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Unknown error");

      // Don't retry on auth errors
      if (error instanceof VolcVideoApiError && error.errorCode === "authentication_error") {
        throw error;
      }

      // Abort errors shouldn't be retried
      if ((error as Error).name === "AbortError") {
        throw new VolcVideoApiError("Request timed out");
      }

      // Retry for other errors
      if (attempt < MAX_RETRIES) {
        console.warn(`Volc Video API attempt ${attempt} failed, retrying...`, error);
        await sleep(RETRY_DELAY_MS * attempt);
      }
    }
  }

  clearTimeout(timeoutId);
  throw new VolcVideoApiError(
    `Failed after ${MAX_RETRIES} attempts: ${lastError?.message}`
  );
}

/**
 * Query the status of a video generation task
 * @param taskId - The task ID to query
 * @returns Current status and video URL (if completed)
 */
export async function getVideoTaskStatus(taskId: string): Promise<VideoStatusResult> {
  if (!isVolcVideoConfigured()) {
    throw new VolcVideoApiError("Volcano Engine video generation is not configured. Please set VOLC_API_KEY.");
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let lastError: Error | null = null;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      const response = await fetch(`${VOLC_VIDEO_TASKS_URL}/${taskId}`, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${VOLC_API_KEY}`,
        },
        signal: controller.signal,
      });

      const data: GetTaskResponse = await response.json();

      // Check for API error
      if (data.error) {
        // Task failed
        return {
          taskId: data.id,
          status: "failed",
          errorMessage: data.error.message,
        };
      }

      if (!response.ok) {
        throw new VolcVideoApiError(
          `HTTP error: ${response.status}`,
          response.status
        );
      }

      clearTimeout(timeoutId);

      // Log raw status for debugging
      console.log(`Video task ${taskId} raw status:`, data.status);

      // Map status
      let status: VideoTaskStatus = "pending";
      if (data.status === "RUNNING" || data.status === "processing" || data.status === "running") {
        status = "processing";
      } else if (data.status === "SUCCESS" || data.status === "completed" || data.status === "succeeded") {
        status = "completed";
      } else if (data.status === "FAILED" || data.status === "failed") {
        status = "failed";
      }

      // Get video URL - can be in content.video_url or output.url
      const videoUrl = data.content?.video_url || data.output?.url;

      return {
        taskId: data.id,
        status,
        videoUrl,
      };
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Unknown error");

      // Don't retry on auth errors
      if (error instanceof VolcVideoApiError && error.errorCode === "authentication_error") {
        throw error;
      }

      // Abort errors shouldn't be retried
      if ((error as Error).name === "AbortError") {
        throw new VolcVideoApiError("Request timed out");
      }

      // Retry for other errors
      if (attempt < MAX_RETRIES) {
        console.warn(`Volc Video Status API attempt ${attempt} failed, retrying...`, error);
        await sleep(RETRY_DELAY_MS * attempt);
      }
    }
  }

  clearTimeout(timeoutId);
  throw new VolcVideoApiError(
    `Failed after ${MAX_RETRIES} attempts: ${lastError?.message}`
  );
}

/**
 * Wait for a video task to complete
 * @param taskId - The task ID to wait for
 * @param options - Polling options
 * @returns Final status with video URL
 */
export async function waitForVideoTask(
  taskId: string,
  options: {
    pollIntervalMs?: number;
    maxWaitMs?: number;
    onProgress?: (status: string) => void;
  } = {}
): Promise<VideoStatusResult> {
  const pollInterval = options.pollIntervalMs ?? 5000; // Default 5 seconds
  const maxWait = options.maxWaitMs ?? 600000; // Default 10 minutes
  const startTime = Date.now();

  while (Date.now() - startTime < maxWait) {
    const status = await getVideoTaskStatus(taskId);

    if (options.onProgress) {
      options.onProgress(status.status);
    }

    if (status.status === "completed") {
      return status;
    }

    if (status.status === "failed") {
      throw new VolcVideoApiError(
        status.errorMessage || "Video generation failed"
      );
    }

    await sleep(pollInterval);
  }

  throw new VolcVideoApiError(
    `Video generation timed out after ${maxWait / 1000} seconds`
  );
}

/**
 * Download video from URL and return as buffer
 * @param videoUrl - URL of the video
 * @returns Video buffer
 */
export async function downloadVideo(videoUrl: string): Promise<Buffer> {
  const response = await fetch(videoUrl);

  if (!response.ok) {
    throw new VolcVideoApiError(`Failed to download video: ${response.status}`);
  }

  const arrayBuffer = await response.arrayBuffer();
  return Buffer.from(arrayBuffer);
}
