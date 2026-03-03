import type { project_stage } from "@/types/database";

/**
 * Stage configuration for display
 */
const STAGES: {
  id: project_stage;
  label: string;
  description: string;
}[] = [
  { id: "draft", label: "草稿", description: "准备故事" },
  { id: "scenes", label: "分镜", description: "拆解场景" },
  { id: "images", label: "图片", description: "生成图片" },
  { id: "videos", label: "视频", description: "生成视频" },
  { id: "completed", label: "完成", description: "项目完成" },
];

interface StageIndicatorProps {
  currentStage: project_stage;
}

/**
 * Stage indicator component showing project progress.
 */
export function StageIndicator({ currentStage }: StageIndicatorProps) {
  const currentIndex = STAGES.findIndex((s) => s.id === currentStage);

  return (
    <div className="w-full">
      {/* Desktop view */}
      <div className="hidden items-center justify-between sm:flex">
        {STAGES.map((stage, index) => {
          const isCompleted = index < currentIndex;
          const isCurrent = index === currentIndex;
          const isLast = index === STAGES.length - 1;

          return (
            <div key={stage.id} className="flex flex-1 items-center">
              {/* Stage circle */}
              <div className="flex flex-col items-center">
                <div
                  className={`flex h-10 w-10 items-center justify-center rounded-full border-2 transition-colors ${
                    isCompleted
                      ? "border-green-500 bg-green-500 text-white"
                      : isCurrent
                        ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                        : "border-zinc-300 bg-white text-zinc-400 dark:border-zinc-600 dark:bg-zinc-900"
                  }`}
                >
                  {isCompleted ? (
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
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  ) : (
                    <span className="text-sm font-medium">{index + 1}</span>
                  )}
                </div>
                <div className="mt-2 text-center">
                  <p
                    className={`text-sm font-medium ${
                      isCurrent
                        ? "text-zinc-900 dark:text-zinc-100"
                        : isCompleted
                          ? "text-green-600 dark:text-green-400"
                          : "text-zinc-400"
                    }`}
                  >
                    {stage.label}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {stage.description}
                  </p>
                </div>
              </div>

              {/* Connector line */}
              {!isLast && (
                <div
                  className={`mx-2 h-0.5 flex-1 rounded-full ${
                    index < currentIndex
                      ? "bg-green-500"
                      : "bg-zinc-200 dark:bg-zinc-700"
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Mobile view */}
      <div className="sm:hidden">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {STAGES[currentIndex]?.label}
          </span>
          <span className="text-sm text-zinc-500">
            {currentIndex + 1} / {STAGES.length}
          </span>
        </div>
        <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
          <div
            className="h-full rounded-full bg-zinc-900 transition-all dark:bg-zinc-100"
            style={{
              width: `${((currentIndex + 1) / STAGES.length) * 100}%`,
            }}
          />
        </div>
        <div className="mt-2 flex justify-between">
          {STAGES.map((stage, index) => (
            <div
              key={stage.id}
              className={`h-1.5 w-1.5 rounded-full ${
                index <= currentIndex
                  ? "bg-zinc-900 dark:bg-zinc-100"
                  : "bg-zinc-300 dark:bg-zinc-600"
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
