import { ProjectListSkeleton } from "@/components/ui/Skeleton";

/**
 * Projects page loading component.
 */
export default function ProjectsLoading() {
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
        <div className="mx-auto w-full max-w-6xl">
          {/* Header */}
          <div className="mb-8">
            <div className="mb-2 h-9 w-32 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
            <div className="h-5 w-24 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
          </div>

          {/* Project list skeleton */}
          <ProjectListSkeleton count={6} />
        </div>
      </main>
    </div>
  );
}
