/**
 * Zhipu AI API wrapper for GLM model interactions.
 * Handles chat completions for story-to-scenes conversion.
 */

import type {
  ZhipuChatMessage,
  ZhipuChatCompletionResponse,
  SceneDescription,
  StoryToScenesResult,
} from "@/types/ai";

// Configuration
const ZHIPU_API_KEY = process.env.ZHIPU_API_KEY;
const ZHIPU_BASE_URL = process.env.ZHIPU_BASE_URL || "https://open.bigmodel.cn/api/paas/v4";
const ZHIPU_MODEL = process.env.ZHIPU_MODEL || "glm-4";

// Retry configuration
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;
const REQUEST_TIMEOUT_MS = 60000;

/**
 * Custom error class for Zhipu API errors
 */
export class ZhipuApiError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public errorCode?: string
  ) {
    super(message);
    this.name = "ZhipuApiError";
  }
}

/**
 * Sleep utility for retry delays
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Check if the API key is configured
 */
export function isZhipuConfigured(): boolean {
  return !!ZHIPU_API_KEY;
}

/**
 * Story-to-scenes prompt template
 * Converts a user story into a structured list of scene descriptions
 */
const STORY_TO_SCENES_SYSTEM_PROMPT = `你是一个专业的视频脚本编剧。你的任务是将用户提供的短故事拆分成适合制作短视频的独立场景。

## 输出要求
1. 将故事拆分为 4-8 个场景（根据故事长度调整）
2. 每个场景应该：
   - 有清晰的视觉描述
   - 包含场景中的人物、动作、环境
   - 适合 5-10 秒的视频展示
   - 场景之间有连贯性

3. 必须以 JSON 格式输出，格式如下：
{
  "scenes": [
    {
      "order_index": 1,
      "description": "场景的详细视觉描述"
    }
  ]
}

## 注意事项
- 不要输出任何额外文字，只输出 JSON
- 确保每个场景描述足够详细，可以用于生成图片
- 场景描述应该包含：场景环境、人物动作、情绪氛围、光影效果`;

const STORY_TO_SCENES_USER_PROMPT_TEMPLATE = `请将以下故事拆分为视频场景：

{story}

{styleGuidance}`;

/**
 * Build style guidance based on selected style
 */
function buildStyleGuidance(style?: string): string {
  const styleMap: Record<string, string> = {
    realistic: "风格指导：写实风格，真实感强，自然光影",
    anime: "风格指导：日本动漫风格，色彩鲜艳，线条清晰",
    cartoon: "风格指导：卡通风格，夸张可爱，色彩明亮",
    cinematic: "风格指导：电影质感，大气磅礴，专业运镜",
    watercolor: "风格指导：水彩画风格，柔和淡雅，艺术感强",
    oil_painting: "风格指导：油画风格，厚重质感，色彩浓郁",
    sketch: "风格指导：素描风格，线条为主，黑白灰调",
    cyberpunk: "风格指导：赛博朋克风格，霓虹灯光，科技感",
    fantasy: "风格指导：奇幻风格，魔法元素，梦幻色彩",
    scifi: "风格指导：科幻风格，未来感，高科技元素",
  };

  if (style && styleMap[style]) {
    return `\n${styleMap[style]}`;
  }
  return "\n风格指导：写实风格";
}

/**
 * Parse JSON response from the model
 */
function parseScenesJson(content: string): StoryToScenesResult {
  // Try to extract JSON from the response
  const jsonMatch = content.match(/\{[\s\S]*\}/);
  if (!jsonMatch) {
    throw new ZhipuApiError("Failed to parse scenes from response: no JSON found");
  }

  try {
    const result = JSON.parse(jsonMatch[0]) as StoryToScenesResult;

    // Validate the structure
    if (!result.scenes || !Array.isArray(result.scenes)) {
      throw new ZhipuApiError("Invalid response structure: missing scenes array");
    }

    // Ensure each scene has required fields
    result.scenes = result.scenes.map((scene, index) => ({
      order_index: scene.order_index ?? index + 1,
      description: scene.description,
    }));

    return result;
  } catch (e) {
    if (e instanceof ZhipuApiError) throw e;
    throw new ZhipuApiError(`Failed to parse JSON: ${e instanceof Error ? e.message : "Unknown error"}`);
  }
}

/**
 * Make a chat completion request to Zhipu AI
 */
async function chatCompletion(
  messages: ZhipuChatMessage[],
  options: {
    temperature?: number;
    maxTokens?: number;
  } = {}
): Promise<ZhipuChatCompletionResponse> {
  if (!ZHIPU_API_KEY) {
    throw new ZhipuApiError("ZHIPU_API_KEY is not configured");
  }

  const requestBody = {
    model: ZHIPU_MODEL,
    messages,
    temperature: options.temperature ?? 0.7,
    max_tokens: options.maxTokens ?? 4096,
    stream: false,
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let lastError: Error | null = null;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      const response = await fetch(`${ZHIPU_BASE_URL}/chat/completions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${ZHIPU_API_KEY}`,
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new ZhipuApiError(
          errorData.error?.message || `HTTP error ${response.status}`,
          response.status,
          errorData.error?.code
        );
      }

      clearTimeout(timeoutId);
      return await response.json();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error("Unknown error");

      // Don't retry on certain errors
      if (error instanceof ZhipuApiError) {
        if (error.statusCode === 401 || error.statusCode === 403) {
          throw error; // Auth errors shouldn't be retried
        }
      }

      // Abort errors shouldn't be retried
      if ((error as Error).name === "AbortError") {
        throw new ZhipuApiError("Request timed out");
      }

      // Retry for other errors
      if (attempt < MAX_RETRIES) {
        console.warn(`Zhipu API attempt ${attempt} failed, retrying...`, error);
        await sleep(RETRY_DELAY_MS * attempt);
      }
    }
  }

  clearTimeout(timeoutId);
  throw new ZhipuApiError(
    `Failed after ${MAX_RETRIES} attempts: ${lastError?.message}`
  );
}

/**
 * Convert a story into scene descriptions
 * @param story - The user's story text
 * @param style - Optional visual style for the scenes
 * @returns Array of scene descriptions
 */
export async function storyToScenes(
  story: string,
  style?: string
): Promise<SceneDescription[]> {
  const styleGuidance = buildStyleGuidance(style);
  const userPrompt = STORY_TO_SCENES_USER_PROMPT_TEMPLATE.replace("{story}", story).replace(
    "{styleGuidance}",
    styleGuidance
  );

  const messages: ZhipuChatMessage[] = [
    { role: "system", content: STORY_TO_SCENES_SYSTEM_PROMPT },
    { role: "user", content: userPrompt },
  ];

  const response = await chatCompletion(messages, {
    temperature: 0.8,
    maxTokens: 4096,
  });

  const content = response.choices[0]?.message?.content;
  if (!content) {
    throw new ZhipuApiError("Empty response from model");
  }

  const result = parseScenesJson(content);
  return result.scenes;
}

/**
 * Regenerate scenes with additional guidance
 * @param story - The original story text
 * @param style - Visual style for the scenes
 * @param previousScenes - Previously generated scenes (for reference)
 * @param feedback - User feedback for improvement
 */
export async function regenerateScenes(
  story: string,
  style?: string,
  previousScenes?: SceneDescription[],
  feedback?: string
): Promise<SceneDescription[]> {
  const styleGuidance = buildStyleGuidance(style);

  let additionalContext = "";
  if (previousScenes && previousScenes.length > 0) {
    additionalContext += `\n\n之前生成的场景（供参考）：\n${previousScenes
      .map((s) => `场景 ${s.order_index}: ${s.description}`)
      .join("\n")}`;
  }

  if (feedback) {
    additionalContext += `\n\n用户反馈（请根据此改进）：${feedback}`;
  }

  const userPrompt = `请将以下故事拆分为视频场景${additionalContext}：

${story}

${styleGuidance}`;

  const messages: ZhipuChatMessage[] = [
    { role: "system", content: STORY_TO_SCENES_SYSTEM_PROMPT },
    { role: "user", content: userPrompt },
  ];

  const response = await chatCompletion(messages, {
    temperature: 0.9,
    maxTokens: 4096,
  });

  const content = response.choices[0]?.message?.content;
  if (!content) {
    throw new ZhipuApiError("Empty response from model");
  }

  const result = parseScenesJson(content);
  return result.scenes;
}
