/**
 * Global loading component.
 * Displays while page content is being loaded.
 */
export default function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950">
      <div className="flex flex-col items-center gap-4">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-zinc-200 border-t-zinc-900 dark:border-zinc-700 dark:border-t-zinc-100" />
        <p className="text-sm text-zinc-500 dark:text-zinc-400">加载中...</p>
      </div>
    </div>
  );
}
