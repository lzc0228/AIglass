"use client";

import { useState } from "react";
import { SceneDescriptionCard } from "./SceneDescriptionCard";
import type { Scene } from "@/types/database";

interface SceneDescriptionListProps {
  projectId: string;
  scenes: Scene[];
}

/**
 * Scene description list component.
 * Displays all scenes with bulk actions.
 */
export function SceneDescriptionList({
  projectId,
  scenes,
}: SceneDescriptionListProps) {
  const [localScenes, setLocalScenes] = useState(scenes);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [isConfirmingAll, setIsConfirmingAll] = useState(false);

  const confirmedCount = localScenes.filter(
    (s) => s.description_confirmed
  ).length;
  const allConfirmed = confirmedCount === localScenes.length;

  const handleConfirmScene = async (sceneId: string) => {
    const response = await fetch(`/api/scenes/${sceneId}/confirm-description`, {
      method: "POST",
    });

    if (!response.ok) {
      throw new Error("Failed to confirm scene");
    }

    setLocalScenes((prev) =>
      prev.map((s) =>
        s.id === sceneId ? { ...s, description_confirmed: true } : s
      )
    );
  };

  const handleUpdateScene = async (sceneId: string, description: string) => {
    const response = await fetch(`/api/scenes/${sceneId}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ description }),
    });

    if (!response.ok) {
      throw new Error("Failed to update scene");
    }

    setLocalScenes((prev) =>
      prev.map((s) =>
        s.id === sceneId ? { ...s, description } : s
      )
    );
  };

  const handleConfirmAll = async () => {
    setIsConfirmingAll(true);
    try {
      const response = await fetch("/api/scenes/confirm-all-descriptions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ projectId }),
      });

      if (!response.ok) {
        throw new Error("Failed to confirm all scenes");
      }

      // Refresh the page to show the next stage (images)
      window.location.reload();
    } catch (error) {
      console.error("Failed to confirm all scenes:", error);
      setIsConfirmingAll(false);
    }
  };

  const handleRegenerate = async () => {
    if (!confirm("确定要重新生成分镜吗？当前的分镜将被删除。")) {
      return;
    }

    setIsRegenerating(true);
    try {
      const response = await fetch("/api/generate/scenes/regenerate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ projectId }),
      });

      if (!response.ok) {
        throw new Error("Failed to regenerate scenes");
      }

      const { scenes: newScenes } = await response.json();
      setLocalScenes(newScenes);
    } catch (error) {
      console.error("Failed to regenerate scenes:", error);
    } finally {
      setIsRegenerating(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Progress */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm text-zinc-600 dark:text-zinc-400">
            已确认 {confirmedCount} / {localScenes.length} 个分镜
          </span>
          {allConfirmed && (
            <span className="text-sm text-green-600 dark:text-green-400">
              ✓ 全部确认
            </span>
          )}
        </div>
      </div>

      {/* Scene Cards */}
      <div className="space-y-3">
        {localScenes.map((scene) => (
          <SceneDescriptionCard
            key={scene.id}
            scene={scene}
            onConfirm={handleConfirmScene}
            onUpdate={handleUpdateScene}
          />
        ))}
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-3 border-t border-zinc-200 pt-4 dark:border-zinc-800 sm:flex-row sm:justify-between">
        <button
          onClick={handleRegenerate}
          disabled={isRegenerating}
          className="flex items-center justify-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          <svg
            className={`h-4 w-4 ${isRegenerating ? "animate-spin" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
          {isRegenerating ? "重新生成中..." : "重新生成分镜"}
        </button>

        {!allConfirmed && (
          <button
            onClick={handleConfirmAll}
            disabled={isConfirmingAll}
            className="flex items-center justify-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
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
                确认所有分镜
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
