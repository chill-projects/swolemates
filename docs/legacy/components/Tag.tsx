import type { ComponentPropsWithoutRef } from "react";

export function Tag({ className = "", ...props }: ComponentPropsWithoutRef<"span">) {
  return (
    <span
      className={`inline-block rounded-full bg-teal-pale px-2.5 py-1 font-mono text-[11px] tracking-wide text-teal uppercase ${className}`}
      {...props}
    />
  );
}
