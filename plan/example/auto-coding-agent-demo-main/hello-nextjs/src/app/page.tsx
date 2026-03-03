import { Header } from "@/components/layout/Header";
import { createClient } from "@/lib/supabase/server";
import Link from "next/link";

export default async function Home() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 dark:bg-zinc-950">
      <Header user={user} />
      <main className="flex flex-1 flex-col items-center justify-center px-4 py-16">
        <div className="max-w-2xl text-center">
          <h1 className="mb-4 text-4xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">
            故事转视频生成平台
          </h1>
          <p className="mb-8 text-lg text-zinc-600 dark:text-zinc-400">
            输入您的故事，AI 将自动为您生成精美的分镜图片和视频
          </p>

          {user ? (
            <div className="flex flex-col items-center gap-4">
              <p className="text-zinc-600 dark:text-zinc-400">
                欢迎回来，{user.email}
              </p>
              <div className="flex gap-4">
                <Link
                  href="/projects"
                  className="flex h-12 items-center justify-center rounded-lg bg-zinc-900 px-6 text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
                >
                  查看我的项目
                </Link>
                <Link
                  href="/create"
                  className="flex h-12 items-center justify-center rounded-lg border border-zinc-300 bg-white px-6 text-sm font-medium text-zinc-900 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800"
                >
                  创建新项目
                </Link>
              </div>
            </div>
          ) : (
            <div className="flex justify-center gap-4">
              <Link
                href="/login"
                className="flex h-12 items-center justify-center rounded-lg bg-zinc-900 px-6 text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                登录
              </Link>
              <Link
                href="/register"
                className="flex h-12 items-center justify-center rounded-lg border border-zinc-300 bg-white px-6 text-sm font-medium text-zinc-900 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800"
              >
                注册
              </Link>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
