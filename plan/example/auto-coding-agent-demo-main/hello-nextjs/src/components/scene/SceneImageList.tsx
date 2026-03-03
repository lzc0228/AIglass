"use client";

import { useState, useMemo, useEffect } from "react";
import { SceneImageCard } from "./SceneImageCard";
import { useSignedUrls } from "@/hooks/useSignedUrls";
import type { Scene, Image as ImageType } from "@/types/database";

type SceneWithImages = Scene & { images: ImageType[] };

interface SceneImageListProps {
  projectId: string;
  scenes: SceneWithImages[];
}

/**
 * Scene image list component.
 * Displays all scenes with their images and bulk actions.
 */
export function SceneImageList({ projectId, scenes }: SceneImageListProps) {
  const [localScenes, setLocalScenes] = useState(scenes);
  const [isGeneratingAll, setIsGeneratingAll] = useState(false);
  const [isConfirmingAll, setIsConfirmingAll] = useState(false);

  // Resume polling for any images that are still processing when component mounts
  useEffect(() => {
    localScenes.forEach((scene) => {
      if (scene.image_status === "processing") {
        // Resume polling for this image
        pollForImageCompletion(scene.id);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount

  // Collect all storage paths for images
  const storagePaths = useMemo(() => {
    return localScenes
      .filter((s) => s.images.length > 0 && s.images[0].storage_path)
      .map((s) => s.images[0].storage_path);
  }, [localScenes]);

  // Fetch signed URLs for all images
  const { urls: signedUrls } = useSignedUrls({ paths: storagePaths });

  const confirmedCount = localScenes.filter((s) => s.image_confirmed).length;
  const completedCount = localScenes.filter(
    (s) => s.image_status === "completed"
  ).length;
  const allConfirmed = confirmedCount === localScenes.length;
  const canConfirmAll = completedCount === localScenes.length && !allConfirmed;

  const handleGenerateImage = async (sceneId: string) => {
    const response = await fetch(`/api/generate/image/${sceneId}`, {
      method: "POST",
    });

    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error ?? "Failed to generate image");
    }

    // Update local state to show processing
    setLocalScenes((prev) =>
      prev.map((s) =>
        s.id === sceneId ? { ...s, image_status: "processing" } : s
      )
    );

    // Poll for completion (simple approach)
    pollForImageCompletion(sceneId);
  };

  const pollForImageCompletion = async (sceneId: string) => {
    const maxAttempts = 60; // 5 minutes max
    const interval = 5000; // 5 seconds

    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((resolve) => setTimeout(resolve, interval));

      try {
        const response = await fetch(`/api/projects/${projectId}`);
        if (!response.ok) continue;

        const { project } = await response.json();
        const scene = project.scenes.find((s: SceneWithImages) => s.id === sceneId);

        if (scene?.image_status === "completed") {
          setLocalScenes((prev) =>
            prev.map((s) =>
              s.id === sceneId
                ? { ...s, image_status: "completed", images: scene.images }
                : s
            )
          );
          return;
        }

        if (scene?.image_status === "failed") {
          setLocalScenes((prev) =>
            prev.map((s) =>
              s.id === sceneId ? { ...s, image_status: "failed" } : s
            )
          );
          return;
        }
      } catch (error) {
        console.error("Poll error:", error);
      }
    }
  };

  const handleConfirmImage = async (sceneId: string) => {
    const response = await fetch(`/api/scenes/${sceneId}/confirm-image`, {
      method: "POST",
    });

    if (!response.ok) {
      throw new Error("Failed to confirm image");
    }

    setLocalScenes((prev) =>
      prev.map((s) =>
        s.id === sceneId ? { ...s, image_confirmed: true } : s
      )
    );
  };

  const handleGenerateAll = async () => {
    setIsGeneratingAll(true);
    try {
      const response = await fetch("/api/generate/images", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ projectId }),
      });

      if (!response.ok) {
        throw new Error("Failed to generate images");
      }

      // Start polling for all scenes
      localScenes.forEach((scene) => {
        if (scene.image_status === "pending") {
          setLocalScenes((prev) =>
            prev.map((s) =>
              s.id === scene.id ? { ...s, image_status: "processing" } : s
            )
          );
          pollForImageCompletion(scene.id);
        }
      });
    } catch (error) {
      console.error("Failed to generate all images:", error);
    } finally {
      setIsGeneratingAll(false);
    }
  };

  const handleConfirmAll = async () => {
    setIsConfirmingAll(true);
    try {
      const response = await fetch("/api/scenes/confirm-all-images", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ projectId }),
      });

      if (!response.ok) {
        throw new Error("Failed to confirm all images");
      }

      // Refresh the page to show the next stage (videos)
      window.location.reload();
    } catch (error) {
      console.error("Failed to confirm all images:", error);
      setIsConfirmingAll(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Progress */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <span className="text-sm text-zinc-600 dark:text-zinc-400">
            已确认 {confirmedCount} / {localScenes.length} 张图片
          </span>
          {allConfirmed && (
            <span className="text-sm text-green-600 dark:text-green-400">
              ✓ 全部确认
            </span>
          )}
        </div>
      </div>

      {/* Generate All Button */}
      {!allConfirmed && (
        <div className="flex gap-3">
          <button
            onClick={handleGenerateAll}
            disabled={isGeneratingAll}
            className="flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            <svg
              className={`h-4 w-4 ${isGeneratingAll ? "animate-spin" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
            {isGeneratingAll ? "生成中..." : "生成所有图片"}
          </button>
        </div>
      )}

      {/* Scene Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {localScenes.map((scene) => {
          const storagePath = scene.images[0]?.storage_path;
          const signedUrl = storagePath ? signedUrls[storagePath] : undefined;

          return (
            <SceneImageCard
              key={scene.id}
              scene={scene}
              signedUrl={signedUrl}
              onGenerate={handleGenerateImage}
              onConfirm={handleConfirmImage}
            />
          );
        })}
      </div>

      {/* Confirm All Button */}
      {canConfirmAll && (
        <div className="flex justify-end border-t border-zinc-200 pt-4 dark:border-zinc-800">
          <button
            onClick={handleConfirmAll}
            disabled={isConfirmingAll}
            className="flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isConfirmingAll ? (
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
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                确认所有图片
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
