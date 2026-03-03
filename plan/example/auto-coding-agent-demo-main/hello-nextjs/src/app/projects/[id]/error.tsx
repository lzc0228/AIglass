"use client";

import { useEffect } from "react";
import Link from "next/link";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Project detail page error boundary.
 * Catches errors specific to the project detail page.
 */
export default function ProjectError({ error, reset }: ErrorProps) {
  useEffect(() => {
    console.error("Project error:", error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 dark:bg-zinc-950">
      <div className="flex flex-1 flex-col items-center justify-center px-4 py-16">
        <div className="max-w-md text-center">
          <div className="mb-6 flex justify-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
              <svg
                className="h-8 w-8 text-red-600 dark:text-red-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>
          </div>

          <h1 className="mb-2 text-2xl font-bold text-zinc-900 dark:text-zinc-100">
            加载项目失败
          </h1>

          <p className="mb-6 text-zinc-600 dark:text-zinc-400">
            无法加载该项目。可能是项目不存在或您没有访问权限。
          </p>

          {error.message && (
            <p className="mb-4 rounded-lg bg-zinc-100 p-3 text-sm text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
              {error.message}
            </p>
          )}

          <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
            <button
              onClick={reset}
              className="rounded-lg bg-zinc-900 px-6 py-3 text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
            >
              重试
            </button>
            <Link
              href="/projects"
              className="rounded-lg border border-zinc-300 bg-white px-6 py-3 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              返回项目列表
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
