import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Combines class names using clsx and merges Tailwind CSS classes using tailwind-merge.
 * This prevents class conflicts and allows for conditional class application.
 *
 * @param inputs - Class values to combine
 * @returns Merged class string
 *
 * @example
 * cn("px-4 py-2", "bg-blue-500", { "text-white": true }) // "px-4 py-2 bg-blue-500 text-white"
 * cn("p-4", "p-2") // "p-2" (tailwind-merge handles conflict)
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
