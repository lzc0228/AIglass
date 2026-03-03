import { Header } from "@/components/layout/Header";
import { ProjectCard } from "@/components/project/ProjectCard";
import { createClient } from "@/lib/supabase/server";
import { getProjectsWithPreview } from "@/lib/db/projects-list";
import { redirect } from "next/navigation";
import Link from "next/link";

interface ProjectsPageProps {
  searchParams: Promise<{
    page?: string;
  }>;
}

export default async function ProjectsPage({ searchParams }: ProjectsPageProps) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // This page is protected by middleware, but we also check here for safety
  if (!user) {
    redirect("/login");
  }

  const resolvedSearchParams = await searchParams;
  const currentPage = parseInt(resolvedSearchParams.page ?? "1", 10);
  const limit = 12;

  const { projects, total } = await getProjectsWithPreview(user.id, {
    page: currentPage,
    limit,
  });

  const totalPages = Math.ceil(total / limit);
  const hasNextPage = currentPage < totalPages;
  const hasPrevPage = currentPage > 1;

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 dark:bg-zinc-950">
      <Header user={user} />
      <main className="flex flex-1 flex-col px-4 py-8">
        <div className="mx-auto w-full max-w-6xl">
          {/* Header */}
          <div className="mb-8 flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-100">
                我的项目
              </h1>
              <p className="mt-1 text-zinc-600 dark:text-zinc-400">
                共 {total} 个项目
              </p>
            </div>
            <Link
              href="/create"
              className="flex h-11 items-center gap-2 rounded-lg bg-zinc-900 px-5 text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
            >
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              创建新项目
            </Link>
          </div>

          {/* Project List */}
          {projects.length > 0 ? (
            <>
              <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {projects.map((project) => (
                  <ProjectCard key={project.id} project={project} />
                ))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="mt-8 flex items-center justify-center gap-2">
                  {hasPrevPage && (
                    <Link
                      href={`/projects?page=${currentPage - 1}`}
                      className="flex h-10 items-center rounded-lg border border-zinc-200 bg-white px-4 text-sm font-medium text-zinc-600 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800"
                    >
                      上一页
                    </Link>
                  )}

                  <div className="flex items-center gap-1 text-sm text-zinc-600 dark:text-zinc-400">
                    <span className="font-medium">{currentPage}</span>
                    <span>/</span>
                    <span>{totalPages}</span>
                  </div>

                  {hasNextPage && (
                    <Link
                      href={`/projects?page=${currentPage + 1}`}
                      className="flex h-10 items-center rounded-lg border border-zinc-200 bg-white px-4 text-sm font-medium text-zinc-600 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800"
                    >
                      下一页
                    </Link>
                  )}
                </div>
              )}
            </>
          ) : (
            /* Empty State */
            <div className="flex flex-col items-center justify-center py-16">
              <div className="mb-4 rounded-full bg-zinc-100 p-4 dark:bg-zinc-800">
                <svg
                  className="h-12 w-12 text-zinc-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                  />
                </svg>
              </div>
              <h2 className="mb-2 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                还没有项目
              </h2>
              <p className="mb-6 text-center text-zinc-600 dark:text-zinc-400">
                创建您的第一个项目，开始将故事转换为视频
              </p>
              <Link
                href="/create"
                className="flex h-11 items-center gap-2 rounded-lg bg-zinc-900 px-5 text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                <svg
                  className="h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 4v16m8-8H4"
                  />
                </svg>
                创建新项目
              </Link>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
