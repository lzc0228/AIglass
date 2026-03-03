"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

export function RegisterForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    // Validate passwords match
    if (password !== confirmPassword) {
      setError("两次输入的密码不一致");
      setIsLoading(false);
      return;
    }

    // Validate password strength
    if (password.length < 6) {
      setError("密码长度至少为6位");
      setIsLoading(false);
      return;
    }

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signUp({
        email,
        password,
      });

      if (error) {
        setError(getErrorMessage(error.message));
        setIsLoading(false);
        return;
      }

      // Registration successful
      setSuccess(true);
      setIsLoading(false);

      // Redirect to login page after 2 seconds
      setTimeout(() => {
        router.push("/login");
      }, 2000);
    } catch {
      setError("注册时发生错误，请稍后重试");
      setIsLoading(false);
    }
  };

  const getErrorMessage = (message: string): string => {
    switch (message) {
      case "User already registered":
        return "该邮箱已被注册";
      case "Password should be at least 6 characters":
        return "密码长度至少为6位";
      case "Invalid email":
        return "请输入有效的邮箱地址";
      case "Signup is disabled":
        return "注册功能已禁用";
      case "Too many requests":
        return "请求过于频繁，请稍后重试";
      default:
        return message || "注册失败，请重试";
    }
  };

  if (success) {
    return (
      <div className="space-y-6">
        <div className="rounded-md bg-green-50 p-4">
          <p className="text-sm text-green-800">
            注册成功！请查收验证邮件后登录。
          </p>
        </div>
        <p className="text-center text-sm text-gray-600">
          即将跳转到登录页面...
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <div className="rounded-md bg-red-50 p-4">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      <div>
        <label
          htmlFor="email"
          className="block text-sm font-medium text-gray-700"
        >
          邮箱
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="请输入邮箱"
        />
      </div>

      <div>
        <label
          htmlFor="password"
          className="block text-sm font-medium text-gray-700"
        >
          密码
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="请输入密码（至少6位）"
        />
      </div>

      <div>
        <label
          htmlFor="confirmPassword"
          className="block text-sm font-medium text-gray-700"
        >
          确认密码
        </label>
        <input
          id="confirmPassword"
          name="confirmPassword"
          type="password"
          autoComplete="new-password"
          required
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          placeholder="请再次输入密码"
        />
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className={cn(
          "w-full rounded-md px-3 py-2 text-sm font-semibold text-white shadow-sm",
          isLoading
            ? "cursor-not-allowed bg-indigo-400"
            : "bg-indigo-600 hover:bg-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
        )}
      >
        {isLoading ? "注册中..." : "注册"}
      </button>

      <p className="text-center text-sm text-gray-600">
        已有账号？{" "}
        <Link
          href="/login"
          className="font-medium text-indigo-600 hover:text-indigo-500"
        >
          立即登录
        </Link>
      </p>
    </form>
  );
}
