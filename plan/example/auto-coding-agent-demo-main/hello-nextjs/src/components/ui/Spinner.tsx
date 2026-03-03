interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizeClasses = {
  sm: "h-4 w-4 border-2",
  md: "h-6 w-6 border-2",
  lg: "h-10 w-10 border-4",
};

/**
 * Spinner loading animation component.
 */
export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  return (
    <div
      className={`animate-spin rounded-full border-zinc-200 border-t-zinc-900 dark:border-zinc-700 dark:border-t-zinc-100 ${sizeClasses[size]} ${className}`}
    />
  );
}
