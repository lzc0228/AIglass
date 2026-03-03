import Link from "next/link";
import Image from "next/image";
import type { ProjectWithPreview } from "@/lib/db/projects-list";
import type { project_stage } from "@/types/database";

/**
 * Stage display configuration
 */
const stageConfig: Record<
  project_stage,
  { label: string; className: string }
> = {
  draft: { label: "草稿", className: "bg-zinc-100 text-zinc-600" },
  scenes: { label: "分镜", className: "bg-blue-100 text-blue-700" },
  images: { label: "图片", className: "bg-purple-100 text-purple-700" },
  videos: { label: "视频", className: "bg-orange-100 text-orange-700" },
  completed: { label: "完成", className: "bg-green-100 text-green-700" },
};

/**
 * Style display names
 */
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

interface ProjectCardProps {
  project: ProjectWithPreview;
}

/**
 * Project card component for displaying in the project list.
 */
export function ProjectCard({ project }: ProjectCardProps) {
  const stage = stageConfig[project.stage];
  const styleName = project.style
    ? styleNames[project.style] ?? project.style
    : null;
  const createdDate = new Date(project.created_at).toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <Link href={`/projects/${project.id}`}>
      <div className="group flex flex-col overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm transition-all hover:shadow-md hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700">
        {/* Preview Image */}
        <div className="relative aspect-video w-full overflow-hidden bg-zinc-100 dark:bg-zinc-800">
          {project.preview_image_url ? (
            <Image
              src={project.preview_image_url}
              alt={project.title}
              fill
              className="object-cover transition-transform group-hover:scale-105"
              sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
              unoptimized
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <svg
                className="h-12 w-12 text-zinc-300 dark:text-zinc-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
              </svg>
            </div>
          )}
          {/* Stage Badge */}
          <div
            className={`absolute right-2 top-2 rounded-full px-2.5 py-1 text-xs font-medium ${stage.className}`}
          >
            {stage.label}
          </div>
        </div>

        {/* Content */}
        <div className="flex flex-1 flex-col p-4">
          <h3 className="mb-1 line-clamp-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            {project.title}
          </h3>

          <div className="mb-2 flex flex-wrap items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
            {styleName && (
              <span className="rounded-md bg-zinc-100 px-2 py-0.5 dark:bg-zinc-800">
                {styleName}
              </span>
            )}
            {project.scene_count > 0 && (
              <span>{project.scene_count} 个分镜</span>
            )}
          </div>

          <p className="mb-3 line-clamp-2 flex-1 text-sm text-zinc-600 dark:text-zinc-400">
            {project.story ?? "暂无故事内容"}
          </p>

          <div className="flex items-center justify-between text-xs text-zinc-400 dark:text-zinc-500">
            <span>创建于 {createdDate}</span>
            <svg
              className="h-4 w-4 transition-transform group-hover:translate-x-1"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
          </div>
        </div>
      </div>
    </Link>
  );
}
