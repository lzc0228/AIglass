"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { VideoStyle } from "@/types/ai";

/**
 * Available style options for video generation
 */
const STYLE_OPTIONS: {
  id: VideoStyle;
  name: string;
  description: string;
}[] = [
  {
    id: "realistic",
    name: "写实风格",
    description: "逼真的照片级效果，接近真实世界",
  },
  {
    id: "anime",
    name: "动漫风格",
    description: "日式动漫风格，色彩鲜艳明亮",
  },
  {
    id: "cartoon",
    name: "卡通风格",
    description: "可爱的卡通风格，适合儿童内容",
  },
  {
    id: "cinematic",
    name: "电影风格",
    description: "电影质感，戏剧性的光影效果",
  },
  {
    id: "watercolor",
    name: "水彩风格",
    description: "柔和的水彩画效果，艺术感强",
  },
  {
    id: "oil_painting",
    name: "油画风格",
    description: "经典油画质感，厚重有层次",
  },
  {
    id: "sketch",
    name: "素描风格",
    description: "黑白线条素描，简洁有韵味",
  },
  {
    id: "cyberpunk",
    name: "赛博朋克",
    description: "未来科技感，霓虹灯光效果",
  },
  {
    id: "fantasy",
    name: "奇幻风格",
    description: "魔法奇幻世界，神秘梦幻",
  },
  {
    id: "scifi",
    name: "科幻风格",
    description: "硬科幻风格，太空与科技",
  },
];

export function CreateProjectForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [story, setStory] = useState("");
  const [style, setStyle] = useState<VideoStyle>("realistic");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!title.trim()) {
      setError("请输入项目标题");
      return;
    }

    if (!story.trim()) {
      setError("请输入故事内容");
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch("/api/projects", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          title: title.trim(),
          story: story.trim(),
          style,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error ?? "创建项目失败");
      }

      const { project } = await response.json();
      router.push(`/projects/${project.id}`);
    } catch (err) {
      console.error("Create project error:", err);
      setError(err instanceof Error ? err.message : "创建项目失败，请重试");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Title Input */}
      <div>
        <label
          htmlFor="title"
          className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
        >
          项目标题
        </label>
        <input
          type="text"
          id="title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="为您的项目起个名字"
          className="w-full rounded-lg border border-zinc-300 bg-white px-4 py-3 text-zinc-900 placeholder-zinc-400 transition-colors focus:border-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-500/20 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:placeholder-zinc-500"
          disabled={isSubmitting}
        />
      </div>

      {/* Story Input */}
      <div>
        <label
          htmlFor="story"
          className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
        >
          故事内容
        </label>
        <textarea
          id="story"
          value={story}
          onChange={(e) => setStory(e.target.value)}
          placeholder="描述您想要转换成视频的故事...&#10;&#10;例如：一只小猫在公园里追逐蝴蝶，最后累得躺在草地上睡着了。"
          rows={6}
          className="w-full resize-none rounded-lg border border-zinc-300 bg-white px-4 py-3 text-zinc-900 placeholder-zinc-400 transition-colors focus:border-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-500/20 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:placeholder-zinc-500"
          disabled={isSubmitting}
        />
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          AI 将自动分析您的故事，拆解成多个分镜场景
        </p>
      </div>

      {/* Style Selector */}
      <div>
        <label className="mb-3 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
          视频风格
        </label>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {STYLE_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setStyle(option.id)}
              disabled={isSubmitting}
              className={`flex flex-col rounded-lg border-2 p-3 text-left transition-all ${
                style === option.id
                  ? "border-zinc-900 bg-zinc-50 dark:border-zinc-100 dark:bg-zinc-800"
                  : "border-zinc-200 bg-white hover:border-zinc-300 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-zinc-600"
              }`}
            >
              <span
                className={`text-sm font-medium ${
                  style === option.id
                    ? "text-zinc-900 dark:text-zinc-100"
                    : "text-zinc-700 dark:text-zinc-300"
                }`}
              >
                {option.name}
              </span>
              <span className="mt-1 text-xs text-zinc-500 dark:text-zinc-400 line-clamp-2">
                {option.description}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Submit Button */}
      <div className="flex items-center justify-end gap-4">
        <button
          type="button"
          onClick={() => router.back()}
          disabled={isSubmitting}
          className="rounded-lg border border-zinc-300 bg-white px-6 py-3 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          取消
        </button>
        <button
          type="submit"
          disabled={isSubmitting}
          className="flex items-center gap-2 rounded-lg bg-zinc-900 px-6 py-3 text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {isSubmitting ? (
            <>
              <svg
                className="h-4 w-4 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              创建中...
            </>
          ) : (
            <>
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              创建项目
            </>
          )}
        </button>
      </div>
    </form>
  );
}
