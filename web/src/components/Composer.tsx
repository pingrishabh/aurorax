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

  // Crucially: sending NEVER blocks the input. You can keep typing and send
  // again while a reply is still streaming (that steers it).
  const send = () => {
    const value = text.trim();
    if (!value) return;
    onSend(value);
    setText("");
    ref.current?.focus();
  };

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
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
            streaming
              ? "Steer the reply in real time — type and send…"
              : "Message the assistant…"
          }
          className="max-h-40 min-h-[44px] flex-1"
        />
        {streaming ? (
          <Button variant="outline" size="icon" onClick={onStop} title="Stop">
            <Square className="h-4 w-4" />
          </Button>
        ) : null}
        <Button size="icon" onClick={send} disabled={!text.trim()} title="Send">
          <ArrowUp className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
