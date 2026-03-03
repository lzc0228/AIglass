import { Header } from "@/components/layout/Header";
import { StageIndicator } from "@/components/project/StageIndicator";
import { DraftStageView } from "@/components/scene/DraftStageView";
import { SceneDescriptionList } from "@/components/scene/SceneDescriptionList";
import { SceneImageList } from "@/components/scene/SceneImageList";
import { SceneVideoList } from "@/components/scene/SceneVideoList";
import { CompletedProjectView } from "@/components/scene/CompletedProjectView";
import { createClient } from "@/lib/supabase/server";
import { getProjectById } from "@/lib/db/projects";
import { redirect, notFound } from "next/navigation";
import Link from "next/link";

interface ProjectDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

export default async function ProjectDetailPage({
  params,
}: ProjectDetailPageProps) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const { id } = await params;

  let project;
  try {
    project = await getProjectById(id, user.id);
  } catch {
    notFound();
  }

  const styleNames: Record<string, string> = {
    realistic: "写实风格",
    anime: "动漫风格",
    cartoon: "卡通风格",
    cinematic: "电影风格",
    watercolor: "水彩风格",
    oil_painting: "油画风格",
    sketch: "素描风格",
    cyberpunk: "赛博朋克",
    fantasy: "奇幻风格",
    scifi: "科幻风格",
  };

  const createdDate = new Date(project.created_at).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const updatedDate = new Date(project.updated_at).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 dark:bg-zinc-950">
      <Header user={user} />
      <main className="flex flex-1 flex-col px-4 py-8">
        <div className="mx-auto w-full max-w-4xl">
          {/* Breadcrumb */}
          <div className="mb-6">
            <Link
              href="/projects"
              className="inline-flex items-center gap-1 text-sm text-zinc-500 transition-colors hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
            >
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
                  d="M15 19l-7-7 7-7"
                />
              </svg>
              返回项目列表
            </Link>
          </div>

          {/* Project Header */}
          <div className="mb-8 rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
                  {project.title}
                </h1>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-zinc-500 dark:text-zinc-400">
                  {project.style && (
                    <span className="rounded-md bg-zinc-100 px-2 py-0.5 dark:bg-zinc-800">
                      {styleNames[project.style] ?? project.style}
                    </span>
                  )}
                  <span>{project.scenes.length} 个分镜</span>
                </div>
              </div>
              <div className="flex gap-2">
                <button className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800">
                  编辑项目
                </button>
                <button className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-600 transition-colors hover:bg-red-50 dark:border-red-900/50 dark:bg-zinc-900 dark:text-red-400 dark:hover:bg-red-900/20">
                  删除项目
                </button>
              </div>
            </div>

            {/* Story */}
            {project.story && (
              <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
                <h3 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                  故事内容
                </h3>
                <p className="text-zinc-600 dark:text-zinc-400">
                  {project.story}
                </p>
              </div>
            )}

            {/* Meta info */}
            <div className="mt-4 flex gap-6 text-sm text-zinc-500 dark:text-zinc-400">
              <span>创建于 {createdDate}</span>
              <span>更新于 {updatedDate}</span>
            </div>
          </div>

          {/* Stage Indicator */}
          <div className="mb-8 rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            <h2 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              项目进度
            </h2>
            <StageIndicator currentStage={project.stage} />
          </div>

          {/* Content based on stage */}
          <div className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            <h2 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              {project.stage === "draft" && "开始创作"}
              {project.stage === "scenes" && "分镜描述"}
              {project.stage === "images" && "图片生成"}
              {project.stage === "videos" && "视频生成"}
              {project.stage === "completed" && "项目完成"}
            </h2>

            {project.stage === "draft" && (
              <DraftStageView projectId={project.id} />
            )}

            {project.stage === "scenes" && (
              <SceneDescriptionList
                projectId={project.id}
                scenes={project.scenes}
              />
            )}

            {project.stage === "images" && (
              <SceneImageList
                projectId={project.id}
                scenes={project.scenes}
              />
            )}

            {project.stage === "videos" && (
              <SceneVideoList
                projectId={project.id}
                scenes={project.scenes}
              />
            )}

            {project.stage === "completed" && (
              <CompletedProjectView
                scenes={project.scenes}
                completedAt={project.updated_at}
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
