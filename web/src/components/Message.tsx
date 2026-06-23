import { Sparkles, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Message as Msg } from "@/lib/types";

export function MessageRow({ message }: { message: Msg }) {
  const isUser = message.role === "user";
  const streaming = message.status === "streaming" || message.status === "pending";

  return (
    <div className="flex gap-3 px-4 py-3">
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border",
          isUser ? "bg-secondary" : "bg-primary text-primary-foreground"
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
      </div>

      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">
            {isUser ? "You" : "Assistant"}
          </span>
          {message.steered && <Badge title="Steered mid-stream">steered</Badge>}
          {message.status === "cancelled" && (
            <Badge className="text-destructive">stopped</Badge>
          )}
        </div>

        {streaming && message.content === "" ? (
          <div className="text-sm italic text-muted-foreground">
            <span className="caret">Thinking</span>
          </div>
        ) : (
          <div
            className={cn(
              "whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground",
              streaming && "caret"
            )}
          >
            {message.content}
          </div>
        )}
      </div>
    </div>
  );
}
