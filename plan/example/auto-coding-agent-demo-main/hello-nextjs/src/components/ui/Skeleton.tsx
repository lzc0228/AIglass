interface SkeletonProps {
  className?: string;
}

/**
 * Skeleton loading placeholder component.
 */
export function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse rounded-md bg-zinc-200 dark:bg-zinc-800 ${className}`}
    />
  );
}

/**
 * Project card skeleton component.
 */
export function ProjectCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      {/* Image */}
      <Skeleton className="aspect-video w-full" />

      {/* Content */}
      <div className="p-4">
        <Skeleton className="mb-2 h-6 w-3/4" />
        <Skeleton className="mb-3 h-4 w-1/2" />
        <Skeleton className="mb-2 h-4 w-full" />
        <Skeleton className="mb-4 h-4 w-2/3" />
        <div className="flex justify-between">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-4" />
        </div>
      </div>
    </div>
  );
}

/**
 * Project list skeleton component.
 */
export function ProjectListSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <ProjectCardSkeleton key={i} />
      ))}
    </div>
  );
}

/**
 * Scene card skeleton component.
 */
export function SceneCardSkeleton() {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-3 flex items-center gap-2">
        <Skeleton className="h-7 w-7 rounded-full" />
        <Skeleton className="h-5 w-20" />
      </div>
      <Skeleton className="mb-2 h-4 w-full" />
      <Skeleton className="mb-4 h-4 w-3/4" />
      <div className="flex justify-end">
        <Skeleton className="h-9 w-20 rounded-lg" />
      </div>
    </div>
  );
}

/**
 * Scene list skeleton component.
 */
export function SceneListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <SceneCardSkeleton key={i} />
      ))}
    </div>
  );
}
