import type { ComponentPropsWithoutRef } from "react";

export function Card({ className = "", ...props }: ComponentPropsWithoutRef<"div">) {
  return (
    <div
      className={`rounded-2xl border border-line bg-card p-4 ${className}`}
      {...props}
    />
  );
}
