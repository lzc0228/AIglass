import { Header } from "@/components/layout/Header";
import { CreateProjectForm } from "@/components/project/CreateProjectForm";
import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

export default async function CreatePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // This page is protected by middleware, but we also check here for safety
  if (!user) {
    redirect("/login");
  }

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 dark:bg-zinc-950">
      <Header user={user} />
      <main className="flex flex-1 flex-col px-4 py-8">
        <div className="mx-auto w-full max-w-3xl">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-100">
              创建新项目
            </h1>
            <p className="mt-2 text-zinc-600 dark:text-zinc-400">
              输入您的故事，选择风格，AI 将为您生成精美的视频
            </p>
          </div>

          {/* Form */}
          <div className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            <CreateProjectForm />
          </div>
        </div>
      </main>
    </div>
  );
}
