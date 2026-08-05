import { cva, type VariantProps } from "class-variance-authority";
import React from "react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "ec-mono inline-flex min-h-7 items-center gap-1.5 border px-2.5 py-1 text-mark font-semibold tracking-[0.08em] uppercase",
  {
    variants: {
      tone: {
        neutral: "border-ink bg-paper text-ink",
        fixture: "border-ink bg-neon text-ink",
        success: "border-verdict-ok bg-paper text-ink",
        /* The absence tones differ by border treatment as well as colour, so
           they stay distinguishable without it. */
        unknown: "border-rule-soft bg-paper text-ink-3",
        unavailable: "border-dashed border-ink bg-paper text-ink",
        notApplicable: "border-dashed border-rule-soft bg-paper text-ink-3",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function StatusBadge({
  className,
  tone,
  ...props
}: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

export function Dot() {
  return (
    <span
      className="inline-block size-1.5 rounded-full bg-current"
      aria-hidden="true"
    />
  );
}
