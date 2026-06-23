import * as React from "react";
import { cn } from "@/lib/utils";

type Tone = "coral" | "muted";

const tones: Record<Tone, string> = {
  coral: "border-transparent bg-primary/15 text-primary",
  muted: "border-border bg-transparent text-muted-foreground",
};

export function Badge({
  className,
  tone = "muted",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.08em]",
        tones[tone],
        className
      )}
      {...props}
    />
  );
}
