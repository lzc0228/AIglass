"use client";

import { useState } from "react";
import { LogoutButton } from "@/components/auth/LogoutButton";
import Link from "next/link";

interface HeaderProps {
  user: {
    email?: string;
  } | null;
}

/**
 * Header component that shows navigation and auth status.
 * Includes responsive mobile menu.
 */
export function Header({ user }: HeaderProps) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const navLinks = user
    ? [
        { href: "/", label: "首页" },
        { href: "/projects", label: "我的项目" },
        { href: "/create", label: "创建项目" },
      ]
    : [{ href: "/", label: "首页" }];

  return (
    <header className="sticky top-0 z-50 w-full border-b border-zinc-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/60 dark:border-zinc-800 dark:bg-zinc-950/95">
      <div className="container flex h-14 items-center justify-between px-4">
        <div className="flex items-center gap-6">
          <Link
            href="/"
            className="text-lg font-semibold text-zinc-900 dark:text-zinc-100"
          >
            Spring FES Video
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden items-center gap-4 md:flex">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>

        {/* Desktop Auth */}
        <div className="hidden items-center gap-4 md:flex">
          {user ? (
            <>
              <span className="text-sm text-zinc-600 dark:text-zinc-400">
                {user.email}
              </span>
              <LogoutButton />
            </>
          ) : (
            <div className="flex items-center gap-2">
              <Link
                href="/login"
                className="flex h-9 items-center justify-center rounded-md px-4 text-sm font-medium text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
              >
                登录
              </Link>
              <Link
                href="/register"
                className="flex h-9 items-center justify-center rounded-md bg-zinc-900 px-4 text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                注册
              </Link>
            </div>
          )}
        </div>

        {/* Mobile Menu Button */}
        <button
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          className="flex h-10 w-10 items-center justify-center rounded-md border border-zinc-200 bg-white transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800 md:hidden"
        >
          <svg
            className="h-5 w-5 text-zinc-600 dark:text-zinc-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            {isMobileMenuOpen ? (
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            ) : (
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 6h16M4 12h16M4 18h16"
              />
            )}
          </svg>
        </button>
      </div>

      {/* Mobile Menu */}
      {isMobileMenuOpen && (
        <div className="border-t border-zinc-200 bg-white px-4 py-4 dark:border-zinc-800 dark:bg-zinc-950 md:hidden">
          <nav className="flex flex-col gap-2">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setIsMobileMenuOpen(false)}
                className="rounded-md px-3 py-2 text-sm text-zinc-600 transition-colors hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <div className="mt-4 border-t border-zinc-200 pt-4 dark:border-zinc-800">
            {user ? (
              <div className="flex flex-col gap-3">
                <span className="px-3 text-sm text-zinc-600 dark:text-zinc-400">
                  {user.email}
                </span>
                <LogoutButton />
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <Link
                  href="/login"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="rounded-md px-3 py-2 text-center text-sm text-zinc-600 transition-colors hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                >
                  登录
                </Link>
                <Link
                  href="/register"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="rounded-md bg-zinc-900 px-3 py-2 text-center text-sm font-medium text-zinc-50 transition-colors hover:bg-zinc-800 dark:bg-zinc-50 dark:text-zinc-900 dark:hover:bg-zinc-200"
                >
                  注册
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
