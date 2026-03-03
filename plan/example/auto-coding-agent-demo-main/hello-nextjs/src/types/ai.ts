/**
 * AI-related type definitions.
 * Types for Zhipu AI and Volcano Engine APIs.
 */

// ============================================
// Zhipu AI Types
// ============================================

export interface ZhipuChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ZhipuChatCompletionRequest {
  model: string;
  messages: ZhipuChatMessage[];
  temperature?: number;
  top_p?: number;
  max_tokens?: number;
  stream?: boolean;
}

export interface ZhipuChatCompletionChoice {
  index: number;
  finish_reason: string;
  message: {
    role: string;
    content: string;
  };
}

export interface ZhipuChatCompletionResponse {
  id: string;
  created: number;
  model: string;
  choices: ZhipuChatCompletionChoice[];
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface ZhipuError {
  code: string;
  message: string;
}

// ============================================
// Story to Scenes Types
// ============================================

export interface SceneDescription {
  order_index: number;
  description: string;
}

export interface StoryToScenesResult {
  scenes: SceneDescription[];
}

// ============================================
// Volcano Engine Image Generation Types
// ============================================

export interface VolcImageGenerationRequest {
  req_key: string;
  prompt: string;
  negative_prompt?: string;
  style?: string;
  width?: number;
  height?: number;
  seed?: number;
  guidance_scale?: number;
  scheduler?: string;
}

export interface VolcImageGenerationResponse {
  code: number;
  message: string;
  data: {
    binary_data_base64: string[];
    seed?: number;
  };
  status?: string;
  time_usage?: {
    total_time: number;
  };
}

export interface VolcImageError {
  code: number;
  message: string;
}

// ============================================
// Volcano Engine Video Generation Types
// ============================================

export interface VolcVideoGenerationRequest {
  req_key: string;
  prompt?: string;
  image_url?: string;
  negative_prompt?: string;
  seed?: number;
  duration?: number;
}

export interface VolcVideoTaskResponse {
  code: number;
  message: string;
  data: {
    task_id: string;
    status: string;
  };
}

export interface VolcVideoTaskStatusResponse {
  code: number;
  message: string;
  data: {
    task_id: string;
    status: "pending" | "processing" | "completed" | "failed";
    progress?: number;
    video_url?: string;
    error_message?: string;
  };
}

export interface VolcVideoError {
  code: number;
  message: string;
}

// ============================================
// API Configuration Types
// ============================================

export interface AIConfig {
  zhipu: {
    apiKey: string;
    baseUrl: string;
    model: string;
  };
  volcano: {
    accessKey: string;
    secretKey: string;
    baseUrl: string;
    region: string;
  };
}

// ============================================
// Style Types
// ============================================

export type VideoStyle =
  | "realistic"
  | "anime"
  | "cartoon"
  | "cinematic"
  | "watercolor"
  | "oil_painting"
  | "sketch"
  | "cyberpunk"
  | "fantasy"
  | "scifi";

export interface StyleOption {
  id: VideoStyle;
  name: string;
  description: string;
  prompt_suffix: string;
}
