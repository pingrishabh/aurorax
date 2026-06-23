import { CornerDownRight, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { AssistantMark } from "./Logo";
import { cn } from "@/lib/utils";
import type { Message } from "@/lib/types";

// A "turn" groups one user prompt, any steering messages that adjusted it, and
// the single assistant reply. Steers nest under the prompt; the reply is always
// rendered last.
export interface TurnGroup {
  key: string;
  prompt?: Message;
  steers: Message[];
  reply?: Message;
}

export function groupTurns(messages: Message[]): TurnGroup[] {
  const map = new Map<string, TurnGroup>();
  const order: string[] = [];
  for (const m of messages) {
    const key = m.turn_id ?? m.id;
    let g = map.get(key);
    if (!g) {
      g = { key, steers: [] };
      map.set(key, g);
      order.push(key);
    }
    if (m.role === "assistant") g.reply = m;
    else if (m.is_steer) g.steers.push(m);
    else g.prompt = m;
  }
  return order.map((k) => map.get(k)!);
}

function Avatar({ kind }: { kind: "user" | "assistant" }) {
  if (kind === "assistant") {
    return <AssistantMark className="h-8 w-8 shrink-0 text-[13px]" />;
  }
  return (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-card text-muted-foreground">
      <User className="h-4 w-4" />
    </div>
  );
}

function Reply({ message }: { message: Message }) {
  const streaming = message.status === "streaming" || message.status === "pending";
  const thinking = streaming && message.content === "";
  return (
    <div className="flex gap-3 pt-5">
      <Avatar kind="assistant" />
      <div className="min-w-0 flex-1 pt-1">
        <div className="mb-1.5 flex items-center gap-2">
          <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
Mock Chat
          </span>
          {message.steered && <Badge tone="coral">steered</Badge>}
          {message.status === "cancelled" && (
            <Badge tone="muted" className="text-destructive">
              stopped
            </Badge>
          )}
        </div>
        {thinking ? (
          <div className="text-[15px] italic text-muted-foreground">
            <span className="dots">Thinking</span>
          </div>
        ) : (
          <div
            className={cn(
              "whitespace-pre-wrap break-words text-[15px] leading-relaxed text-foreground",
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

export function Turn({ group }: { group: TurnGroup }) {
  const { prompt, steers, reply } = group;
  return (
    <div className="px-5">
      {prompt && (
        <div className="flex gap-3 pt-5">
          <Avatar kind="user" />
          <div className="min-w-0 flex-1 pt-1">
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
              You
            </div>
            <div className="whitespace-pre-wrap break-words text-[15px] leading-relaxed text-foreground">
              {prompt.content}
            </div>
          </div>
        </div>
      )}

      {steers.length > 0 && (
        <div className="ml-11 mt-3 space-y-2 border-l border-border pl-4">
          {steers.map((s) => (
            <div
              key={s.id}
              className="flex items-start gap-2 text-sm leading-relaxed text-muted-foreground"
            >
              <CornerDownRight className="mt-[3px] h-3.5 w-3.5 shrink-0 text-primary/70" />
              <span className="min-w-0">{s.content}</span>
            </div>
          ))}
        </div>
      )}

      {reply && <Reply message={reply} />}
    </div>
  );
}
