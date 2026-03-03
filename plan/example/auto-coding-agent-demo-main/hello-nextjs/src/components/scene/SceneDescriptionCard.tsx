"use client";

import { useState } from "react";
import type { Scene } from "@/types/database";

interface SceneDescriptionCardProps {
  scene: Scene;
  onConfirm: (sceneId: string) => Promise<void>;
  onUpdate: (sceneId: string, description: string) => Promise<void>;
}

/**
 * Scene description card component.
 * Displays a single scene's description with edit and confirm functionality.
 */
export function SceneDescriptionCard({
  scene,
  onConfirm,
  onUpdate,
}: SceneDescriptionCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedDescription, setEditedDescription] = useState(scene.description);
  const [isSaving, setIsSaving] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);

  const handleSaveEdit = async () => {
    if (editedDescription.trim() === scene.description) {
      setIsEditing(false);
      return;
    }

    setIsSaving(true);
    try {
      await onUpdate(scene.id, editedDescription.trim());
      setIsEditing(false);
    } catch (error) {
      console.error("Failed to update scene:", error);
      setEditedDescription(scene.description); // Reset on error
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancelEdit = () => {
    setEditedDescription(scene.description);
    setIsEditing(false);
  };

  const handleConfirm = async () => {
    setIsConfirming(true);
    try {
      await onConfirm(scene.id);
    } catch (error) {
      console.error("Failed to confirm scene:", error);
    } finally {
      setIsConfirming(false);
    }
  };

  return (
    <div
      className={`rounded-xl border p-4 transition-colors ${
        scene.description_confirmed
          ? "border-green-200 bg-green-50 dark:border-green-900/50 dark:bg-green-900/20"
          : "border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
      }`}
    >
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-zinc-100 text-sm font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
            {scene.order_index + 1}
          </span>
          <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            分镜 {scene.order_index + 1}
          </span>
          {scene.description_confirmed && (
            <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
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
            </span>
          )}
        </div>

        {!scene.description_confirmed && !isEditing && (
          <button
            onClick={() => setIsEditing(true)}
            className="text-sm text-zinc-500 transition-colors hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            编辑
          </button>
        )}
      </div>

      {/* Description */}
      {isEditing ? (
        <div className="space-y-3">
          <textarea
            value={editedDescription}
            onChange={(e) => setEditedDescription(e.target.value)}
            rows={4}
            className="w-full resize-none rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none focus:ring-2 focus:ring-zinc-500/20 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
            disabled={isSaving}
          />
          <div className="flex justify-end gap-2">
            <button
              onClick={handleCancelEdit}
              disabled={isSaving}
              className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            >
              取消
            </button>
            <button
              onClick={handleSaveEdit}
              disabled={isSaving || !editedDescription.trim()}
              className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
            >
              {isSaving ? "保存中..." : "保存"}
            </button>
          </div>
        </div>
      ) : (
        <p className="text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
          {scene.description}
        </p>
      )}

      {/* Confirm Button */}
      {!scene.description_confirmed && !isEditing && (
        <div className="mt-4 flex justify-end">
          <button
            onClick={handleConfirm}
            disabled={isConfirming}
            className="flex items-center gap-1.5 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
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
        </div>
      )}
    </div>
  );
}
