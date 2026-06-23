import { useEffect, useRef } from "react";
import { MessageRow } from "./Message";
import { Composer } from "./Composer";
import type { Message } from "@/lib/types";

interface Props {
  messages: Message[];
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function ChatPane({ messages, streaming, onSend, onStop }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl py-6">
          {messages.length === 0 ? (
            <div className="px-4 py-20 text-center text-sm text-muted-foreground">
              <p className="text-base font-medium text-foreground">
                Start a conversation
              </p>
              <p className="mt-1">
                Send a message — you can keep typing and steer the reply while it
                streams.
              </p>
            </div>
          ) : (
            messages.map((m) => <MessageRow key={m.id} message={m} />)
          )}
          <div ref={endRef} />
        </div>
      </div>
      <Composer onSend={onSend} onStop={onStop} streaming={streaming} />
    </main>
  );
}
