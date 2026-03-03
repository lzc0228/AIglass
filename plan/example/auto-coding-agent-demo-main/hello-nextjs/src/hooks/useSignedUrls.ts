"use client";

import { useState, useEffect, useCallback } from "react";

interface UseSignedUrlsOptions {
  paths: string[];
  expiresIn?: number;
  enabled?: boolean;
}

interface UseSignedUrlsResult {
  urls: Record<string, string>;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
}

/**
 * Hook to fetch signed URLs for storage paths
 * Automatically refreshes URLs before they expire
 */
export function useSignedUrls({
  paths,
  expiresIn = 3600,
  enabled = true,
}: UseSignedUrlsOptions): UseSignedUrlsResult {
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const fetchUrls = useCallback(async () => {
    if (!enabled || paths.length === 0) {
      return;
    }

    // Filter out empty paths
    const validPaths = paths.filter((p) => p && p.trim() !== "");
    if (validPaths.length === 0) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/storage/signed-urls", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ paths: validPaths, expiresIn }),
      });

      if (!response.ok) {
        throw new Error("Failed to fetch signed URLs");
      }

      const data = await response.json();
      setUrls(data.urls ?? {});
    } catch (err) {
      setError(err instanceof Error ? err : new Error("Unknown error"));
    } finally {
      setLoading(false);
    }
  }, [paths, expiresIn, enabled]);

  useEffect(() => {
    fetchUrls();
  }, [fetchUrls]);

  // Auto-refresh URLs at 80% of expiration time
  useEffect(() => {
    if (!enabled || paths.length === 0) {
      return;
    }

    const refreshTime = expiresIn * 800; // 80% of expiration time in ms
    const interval = setInterval(fetchUrls, refreshTime);

    return () => clearInterval(interval);
  }, [fetchUrls, expiresIn, enabled, paths.length]);

  return {
    urls,
    loading,
    error,
    refresh: fetchUrls,
  };
}

/**
 * Hook to fetch a single signed URL
 */
export function useSignedUrl(
  path: string | null,
  expiresIn?: number
): { url: string | null; loading: boolean; error: Error | null } {
  const paths = path ? [path] : [];
  const { urls, loading, error } = useSignedUrls({ paths, expiresIn });

  return {
    url: path ? urls[path] ?? null : null,
    loading,
    error,
  };
}
