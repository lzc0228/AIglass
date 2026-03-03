"use client";

import { ToastProvider } from "@/components/ui/Toast";
import type { ReactNode } from "react";

/**
 * Client-side providers wrapper.
 * Used to wrap the app with client-side context providers.
 */
export function Providers({ children }: { children: ReactNode }) {
  return <ToastProvider>{children}</ToastProvider>;
}
