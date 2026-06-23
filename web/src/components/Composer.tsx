import { useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  onSend: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
}

export function Composer({ onSend, onStop, streaming }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Sending NEVER blocks the input. You can keep typing and send again while a
  // reply is still streaming, which steers it.
  const send = () => {
    const value = text.trim();
    if (!value) return;
    onSend(value);
    setText("");
    ref.current?.focus();
  };

  return (
    <div className="border-t border-border bg-background px-4 py-4">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2 rounded-2xl border border-border bg-card px-3 py-2.5 transition-colors focus-within:border-primary/60">
          <Textarea
            ref={ref}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder={
              streaming ? "Steer the reply as it streams" : "Message Mock Chat"
            }
            className="max-h-40 min-h-[28px] flex-1 px-1 py-1"
          />
          <div className="flex items-center gap-1.5 pb-0.5">
            {streaming && (
              <Button
                variant="outline"
                size="icon-sm"
                className="rounded-full"
                onClick={onStop}
                title="Stop"
              >
                <Square className="h-3.5 w-3.5" />
              </Button>
            )}
            <Button
              size="icon-sm"
              className="rounded-full"
              onClick={send}
              disabled={!text.trim()}
              title="Send"
            >
              <ArrowUp className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
