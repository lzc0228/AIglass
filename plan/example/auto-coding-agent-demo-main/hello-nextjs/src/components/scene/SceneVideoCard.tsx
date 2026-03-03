"use client";

import { useState } from "react";
import Image from "next/image";
import type { Scene, Image as ImageType, Video } from "@/types/database";

interface SceneVideoCardProps {
  scene: Scene & { images: ImageType[]; videos: Video[] };
  signedImageUrl?: string; // Signed URL for the image
  signedVideoUrl?: string; // Signed URL for the video
  onGenerate: (sceneId: string) => Promise<void>;
  onConfirm: (sceneId: string) => Promise<void>;
}

/**
 * Status display configuration
 */
const statusConfig = {
  pending: { label: "等待生成", className: "bg-zinc-100 text-zinc-600" },
  processing: { label: "生成中", className: "bg-blue-100 text-blue-700" },
  completed: { label: "已完成", className: "bg-green-100 text-green-700" },
  failed: { label: "生成失败", className: "bg-red-100 text-red-700" },
};

/**
 * Scene video card component.
 * Displays a scene's video with generation and confirmation functionality.
 */
export function SceneVideoCard({
  scene,
  signedImageUrl,
  signedVideoUrl,
  onGenerate,
  onConfirm,
}: SceneVideoCardProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);

  const latestImage = scene.images[0];
  const latestVideo = scene.videos[0];
  const imageUrl = signedImageUrl ?? latestImage?.url;
  const videoUrl = signedVideoUrl ?? latestVideo?.url;
  const status = statusConfig[scene.video_status];
  const canConfirm = scene.video_status === "completed" && !scene.video_confirmed;

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      await onGenerate(scene.id);
    } catch (error) {
      console.error("Failed to generate video:", error);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleConfirm = async () => {
    setIsConfirming(true);
    try {
      await onConfirm(scene.id);
    } catch (error) {
      console.error("Failed to confirm video:", error);
    } finally {
      setIsConfirming(false);
    }
  };

  return (
    <div
      className={`overflow-hidden rounded-xl border transition-colors ${
        scene.video_confirmed
          ? "border-green-200 bg-green-50 dark:border-green-900/50 dark:bg-green-900/20"
          : "border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
      }`}
    >
      {/* Video/Image Preview */}
      <div className="relative aspect-video w-full bg-zinc-100 dark:bg-zinc-800">
        {videoUrl ? (
          <video
            src={videoUrl}
            className="h-full w-full object-cover"
            controls
            muted
          />
        ) : imageUrl ? (
          <Image
            src={imageUrl}
            alt={`分镜 ${scene.order_index + 1}`}
            fill
            className="object-cover"
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            unoptimized
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            {scene.video_status === "processing" ? (
              <div className="flex flex-col items-center gap-2">
                <svg
                  className="h-8 w-8 animate-spin text-zinc-400"
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
                <span className="text-sm text-zinc-500">生成中...</span>
              </div>
            ) : (
              <svg
                className="h-12 w-12 text-zinc-300 dark:text-zinc-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                />
              </svg>
            )}
          </div>
        )}

        {/* Status Badge */}
        <div
          className={`absolute right-2 top-2 rounded-full px-2.5 py-1 text-xs font-medium ${status.className}`}
        >
          {status.label}
        </div>

        {/* Scene Number */}
        <div className="absolute bottom-2 left-2 flex h-6 w-6 items-center justify-center rounded-full bg-black/50 text-xs font-medium text-white">
          {scene.order_index + 1}
        </div>

        {/* Play icon overlay for videos */}
        {videoUrl && !scene.video_confirmed && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-black/50">
              <svg
                className="h-6 w-6 text-white"
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <path d="M8 5v14l11-7z" />
              </svg>
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Description */}
        <p className="mb-3 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
          {scene.description}
        </p>

        {/* Actions */}
        <div className="flex items-center justify-between gap-2">
          {!scene.video_confirmed && (
            <>
              {/* Generate/Regenerate Button */}
              {(scene.video_status === "pending" || scene.video_status === "failed") && (
                <button
                  onClick={handleGenerate}
                  disabled={isGenerating}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-2 text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
                >
                  {isGenerating ? (
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
                      生成中...
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
                          d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                        />
                      </svg>
                      {scene.video_status === "failed" ? "重新生成" : "生成视频"}
                    </>
                  )}
                </button>
              )}

              {/* Confirm Button */}
              {canConfirm && (
                <button
                  onClick={handleConfirm}
                  disabled={isConfirming}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isConfirming ? (
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
                      确认中...
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
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                      确认
                    </>
                  )}
                </button>
              )}

              {/* Processing State */}
              {scene.video_status === "processing" && (
                <div className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700 dark:bg-blue-900/20 dark:text-blue-400">
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
                  生成中...
                </div>
              )}
            </>
          )}

          {/* Confirmed State */}
          {scene.video_confirmed && (
            <div className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-green-100 px-3 py-2 text-sm font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
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
                  d="M5 13l4 4L19 7"
                />
              </svg>
              已确认
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
