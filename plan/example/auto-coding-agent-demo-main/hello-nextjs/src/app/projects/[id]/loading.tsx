import { Skeleton } from "@/components/ui/Skeleton";

/**
 * Project detail page loading component.
 */
export default function ProjectDetailLoading() {
  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 dark:bg-zinc-950">
      {/* Header placeholder */}
      <div className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <div className="h-6 w-40 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
          <div className="flex items-center gap-4">
            <div className="h-9 w-16 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
          </div>
        </div>
      </div>

      <main className="flex flex-1 flex-col px-4 py-8">
        <div className="mx-auto w-full max-w-4xl">
          {/* Breadcrumb */}
          <div className="mb-6">
            <Skeleton className="h-5 w-32" />
          </div>

          {/* Project Header */}
          <div className="mb-8 rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
            <div className="mb-4 flex items-start justify-between">
              <div>
                <Skeleton className="mb-2 h-8 w-48" />
                <div className="flex gap-3">
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-5 w-16" />
                </div>
              </div>
              <div className="flex gap-2">
                <Skeleton className="h-10 w-20 rounded-lg" />
                <Skeleton className="h-10 w-20 rounded-lg" />
              </div>
            </div>
            <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
              <Skeleton className="mb-2 h-4 w-16" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="mt-1 h-4 w-3/4" />
            </div>
          </div>

          {/* Stage Indicator */}
          <div className="mb-8 rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
            <Skeleton className="mb-4 h-6 w-24" />
            <div className="flex items-center justify-between">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex flex-col items-center">
                  <Skeleton className="h-10 w-10 rounded-full" />
                  <Skeleton className="mt-2 h-4 w-12" />
                </div>
              ))}
            </div>
          </div>

          {/* Content */}
          <div className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
            <Skeleton className="mb-4 h-6 w-32" />
            <div className="py-8 text-center">
              <Skeleton className="mx-auto mb-4 h-4 w-64" />
              <Skeleton className="mx-auto h-10 w-32 rounded-lg" />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
