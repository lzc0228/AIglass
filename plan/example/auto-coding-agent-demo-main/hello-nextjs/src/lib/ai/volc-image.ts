/**
 * Volcano Engine Image Generation API wrapper.
 * Handles image generation using Doubao Seedream model.
 * API: https://ark.cn-beijing.volces.com/api/v3/images/generations
 */

// Configuration
const VOLC_API_KEY = process.env.VOLC_API_KEY;
const VOLC_IMAGE_BASE_URL = process.env.VOLC_IMAGE_BASE_URL || "https://ark.cn-beijing.volces.com/api/v3/images/generations";
const DEFAULT_MODEL = "doubao-seedream-4-5-251128";

// Retry configuration
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;
const REQUEST_TIMEOUT_MS = 120000; // 2 minutes for image generation

/**
 * Custom error class for Volcano Engine API errors
 */
export class VolcImageApiError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public errorCode?: string
  ) {
    super(message);
    this.name = "VolcImageApiError";
  }
}

/**
 * Sleep utility for retry delays
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Check if the API credentials are configured
 */
export function isVolcImageConfigured(): boolean {
  return !!VOLC_API_KEY;
}

/**
 * Build style prompt suffix based on video style
 */
function buildStylePrompt(style?: string): string {
  const stylePrompts: Record<string, string> = {
    realistic: ", photorealistic, high quality, natural lighting, sharp details",
    anime: ", anime style, vibrant colors, clean lines, Japanese animation",
    cartoon: ", cartoon style, bright colors, playful, exaggerated features",
    cinematic: ", cinematic, dramatic lighting, film grain, professional cinematography",
    watercolor: ", watercolor painting style, soft edges, delicate colors, artistic",
    oil_painting: ", oil painting style, thick brushstrokes, rich colors, classical art",
    sketch: ", pencil sketch style, detailed linework, grayscale, artistic drawing",
    cyberpunk: ", cyberpunk style, neon lights, futuristic, dark atmosphere, tech aesthetic",
    fantasy: ", fantasy style, magical elements, ethereal, dreamlike, mystical",
    scifi: ", sci-fi style, futuristic, high-tech, space age, advanced technology",
  };

  return stylePrompts[style ?? "realistic"] || stylePrompts.realistic;
}

/**
 * API response type
 */
interface ImageGenerationResponse {
  created: number;
  data: Array<{
    url?: string;
    b64_json?: string;
  }>;
  error?: {
    message: string;
    type: string;
    code: string;
  };
}

/**
 * Generate an image from a text description
 * @param prompt - The scene description to generate an image for
 * @param style - Optional visual style
 * @param options - Additional generation options
 * @returns Base64 encoded image data (without data URI prefix)
 */
export async function generateImage(
  prompt: string,
  style?: string,
  options: {
    size?: "1K" | "2K" | "720p" | "1080p";
  } = {}
): Promise<string> {
  if (!isVolcImageConfigured()) {
    throw new VolcImageApiError("Volcano Engine image generation is not configured. Please set VOLC_API_KEY.");
  }

  const stylePrompt = buildStylePrompt(style);
  const fullPrompt = `${prompt}${stylePrompt}`;

  const requestBody = {
    model: DEFAULT_MODEL,
    prompt: fullPrompt,
    size: options.size ?? "2K",
    watermark: false,
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let lastError: Error | null = null;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      const response = await fetch(VOLC_IMAGE_BASE_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${VOLC_API_KEY}`,
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      const data: ImageGenerationResponse = await response.json();

      // Check for API error
      if (data.error) {
        throw new VolcImageApiError(
          data.error.message || `API error: ${data.error.code}`,
          response.status,
          data.error.code
        );
      }

      if (!response.ok) {
        throw new VolcImageApiError(
          `HTTP error: ${response.status}`,
          response.status
        );
      }

      // Get image data - can be URL or base64
      const imageData = data.data?.[0];
      if (!imageData) {
        throw new VolcImageApiError("No image data in response");
      }

      // If URL, download and convert to base64
      if (imageData.url) {
        const imageResponse = await fetch(imageData.url);
        if (!imageResponse.ok) {
          throw new VolcImageApiError("Failed to download generated image");
        }
        const arrayBuffer = await imageResponse.arrayBuffer();
        const base64 = Buffer.from(arrayBuffer).toString("base64");
        clearTimeout(timeoutId);
        return base64;
      }

      // If base64, return directly
      if (imageData.b64_json) {
        clearTimeout(timeoutId);
        return imageData.b64_json;
      }

      throw new VolcImageApiError("No image URL or base64 data in response");
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Unknown error");

      // Don't retry on auth errors
      if (error instanceof VolcImageApiError && error.errorCode === "authentication_error") {
        throw error;
      }

      // Abort errors shouldn't be retried
      if ((error as Error).name === "AbortError") {
        throw new VolcImageApiError("Request timed out");
      }

      // Retry for other errors
      if (attempt < MAX_RETRIES) {
        console.warn(`Volc Image API attempt ${attempt} failed, retrying...`, error);
        await sleep(RETRY_DELAY_MS * attempt);
      }
    }
  }

  clearTimeout(timeoutId);
  throw new VolcImageApiError(
    `Failed after ${MAX_RETRIES} attempts: ${lastError?.message}`
  );
}

/**
 * Generate an image and return as a Buffer
 * @param prompt - The scene description
 * @param style - Optional visual style
 * @param options - Additional generation options
 * @returns Buffer containing the image data
 */
export async function generateImageBuffer(
  prompt: string,
  style?: string,
  options?: {
    size?: "1K" | "2K";
  }
): Promise<Buffer> {
  const base64Data = await generateImage(prompt, style, options);
  return Buffer.from(base64Data, "base64");
}

/**
 * Regenerate an image with different parameters
 * @param prompt - The scene description
 * @param style - Visual style
 * @param options - Additional options
 */
export async function regenerateImage(
  prompt: string,
  style?: string,
  options?: {
    size?: "1K" | "2K";
  }
): Promise<string> {
  // The API generates different images each time by default
  return generateImage(prompt, style, options);
}
