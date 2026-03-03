"use client";

import { useState, useMemo } from "react";
import Image from "next/image";
import { useSignedUrls } from "@/hooks/useSignedUrls";
import type { Scene, Image as ImageType, Video } from "@/types/database";

type SceneWithMedia = Scene & { images: ImageType[]; videos: Video[] };

interface CompletedProjectViewProps {
  scenes: SceneWithMedia[];
  completedAt: string;
}

/**
 * Completed project view component.
 * Displays all scene videos with download options.
 */
export function CompletedProjectView({
  scenes,
  completedAt,
}: CompletedProjectViewProps) {
  const [selectedScene, setSelectedScene] = useState<SceneWithMedia | null>(
    scenes[0] ?? null
  );

  // Collect all storage paths for images and videos
  const storagePaths = useMemo(() => {
    const paths: string[] = [];
    scenes.forEach((scene) => {
      if (scene.images[0]?.storage_path) {
        paths.push(scene.images[0].storage_path);
      }
      if (scene.videos[0]?.storage_path) {
        paths.push(scene.videos[0].storage_path);
      }
    });
    return paths;
  }, [scenes]);

  // Fetch signed URLs for all media
  const { urls: signedUrls } = useSignedUrls({ paths: storagePaths });

  // Helper to get signed URL
  const getSignedUrl = (storagePath: string | undefined): string | undefined => {
    if (!storagePath) return undefined;
    return signedUrls[storagePath];
  };

  const completedDate = new Date(completedAt).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  const handleDownload = (video: Video, sceneIndex: number) => {
    const downloadUrl = getSignedUrl(video.storage_path) ?? video.url;
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = `scene-${sceneIndex + 1}.mp4`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleDownloadAll = async () => {
    for (const scene of scenes) {
      const video = scene.videos[0];
      if (video) {
        handleDownload(video, scene.order_index);
        // Small delay between downloads
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }
  };

  return (
    <div className="space-y-6">
      {/* Completion Info */}
      <div className="flex items-center justify-between rounded-xl border border-green-200 bg-green-50 p-4 dark:border-green-900/50 dark:bg-green-900/20">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-green-500">
            <svg
              className="h-6 w-6 text-white"
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
          </div>
          <div>
            <p className="font-medium text-green-800 dark:text-green-200">
              项目已完成
            </p>
            <p className="text-sm text-green-600 dark:text-green-400">
              完成于 {completedDate}
            </p>
          </div>
        </div>
        <button
          onClick={handleDownloadAll}
          className="flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700"
        >
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
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
            />
          </svg>
          下载所有视频
        </button>
      </div>

      {/* Main Video Display */}
      {selectedScene && selectedScene.videos[0] && (
        <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
          <div className="aspect-video w-full bg-black">
            <video
              key={selectedScene.videos[0].id}
              src={getSignedUrl(selectedScene.videos[0].storage_path) ?? selectedScene.videos[0].url}
              className="h-full w-full"
              controls
              autoPlay
            />
          </div>
          <div className="p-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-100 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                {selectedScene.order_index + 1}
              </span>
              <span className="font-medium text-zinc-900 dark:text-zinc-100">
                分镜 {selectedScene.order_index + 1}
              </span>
            </div>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {selectedScene.description}
            </p>
            <button
              onClick={() =>
                handleDownload(selectedScene.videos[0], selectedScene.order_index)
              }
              className="mt-3 flex items-center gap-1.5 text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            >
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
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                />
              </svg>
              下载此视频
            </button>
          </div>
        </div>
      )}

      {/* Scene Thumbnails */}
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-7">
        {scenes.map((scene) => {
          const video = scene.videos[0];
          const image = scene.images[0];
          const isSelected = selectedScene?.id === scene.id;
          const videoUrl = video ? (getSignedUrl(video.storage_path) ?? video.url) : undefined;
          const imageUrl = image ? (getSignedUrl(image.storage_path) ?? image.url) : undefined;

          return (
            <button
              key={scene.id}
              onClick={() => setSelectedScene(scene)}
              className={`group relative aspect-video overflow-hidden rounded-lg border-2 transition-all ${
                isSelected
                  ? "border-green-500 ring-2 ring-green-500/50"
                  : "border-zinc-200 hover:border-zinc-300 dark:border-zinc-700 dark:hover:border-zinc-600"
              }`}
            >
              {videoUrl ? (
                <video
                  src={videoUrl}
                  className="h-full w-full object-cover"
                  muted
                />
              ) : imageUrl ? (
                <Image
                  src={imageUrl}
                  alt={`分镜 ${scene.order_index + 1}`}
                  fill
                  className="object-cover"
                  sizes="150px"
                  unoptimized
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center bg-zinc-100 dark:bg-zinc-800">
                  <span className="text-xs text-zinc-400">
                    {scene.order_index + 1}
                  </span>
                </div>
              )}
              <div className="absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/30">
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-full bg-white/90 transition-opacity ${
                    isSelected ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                  }`}
                >
                  <svg
                    className="h-4 w-4 text-zinc-900"
                    fill="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </div>
              </div>
              <div className="absolute bottom-1 left-1 flex h-5 w-5 items-center justify-center rounded bg-black/50 text-xs font-medium text-white">
                {scene.order_index + 1}
              </div>
            </button>
          );
        })}
      </div>

      {/* Scene List */}
      <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h3 className="mb-3 font-medium text-zinc-900 dark:text-zinc-100">
          所有分镜
        </h3>
        <div className="space-y-2">
          {scenes.map((scene) => {
            const video = scene.videos[0];

            return (
              <div
                key={scene.id}
                className="flex items-center justify-between rounded-lg border border-zinc-100 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-800/50"
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-200 text-xs font-medium text-zinc-600 dark:bg-zinc-700 dark:text-zinc-400">
                    {scene.order_index + 1}
                  </span>
                  <p className="text-sm text-zinc-600 dark:text-zinc-400 line-clamp-1">
                    {scene.description}
                  </p>
                </div>
                {video && (
                  <button
                    onClick={() => handleDownload(video, scene.order_index)}
                    className="flex items-center gap-1 rounded px-2 py-1 text-xs text-zinc-500 transition-colors hover:bg-zinc-200 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-700 dark:hover:text-zinc-200"
                  >
                    <svg
                      className="h-3.5 w-3.5"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                      />
                    </svg>
                    下载
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
