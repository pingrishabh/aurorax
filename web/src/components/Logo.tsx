import { cn } from "@/lib/utils";

// Neutral Mock Chat mark: a coral tile with a serif monogram. Replaces the
// Anthropic spike glyph while keeping the DESIGN.md colour + type scheme.
export function Logo({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-md bg-primary font-display font-semibold leading-none text-primary-foreground",
        className
      )}
      aria-hidden="true"
    >
      M
    </div>
  );
}

// Tinted circular variant used as the assistant avatar (restrained coral).
export function AssistantMark({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-full bg-primary/15 font-display font-semibold leading-none text-primary",
        className
      )}
      aria-hidden="true"
    >
      M
    </div>
  );
}
