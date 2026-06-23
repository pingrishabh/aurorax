import { useEffect, useRef } from "react";
import { Turn } from "./Turn";
import { Composer } from "./Composer";
import { Logo } from "./Logo";
import { groupTurns } from "@/lib/turns";
import type { Message } from "@/lib/types";

interface Props {
  messages: Message[];
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function ChatPane({ messages, streaming, onSend, onStop }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true); // is the user parked at the bottom?
  const prevLen = useRef(0);

  // Follow the newest content, but only while the user is at the bottom. If they
  // scroll up (e.g. to re-read while a reply is still streaming), stay put. A
  // brand-new message (length grows) always scrolls down.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const grew = messages.length > prevLen.current;
    prevLen.current = messages.length;
    if (grew || pinned.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  };

  const turns = groupTurns(messages);

  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div ref={scrollRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto">
        {turns.length === 0 ? (
          <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center px-6 text-center">
            <Logo className="mb-5 h-11 w-11 text-lg" />
            <h1 className="font-display text-4xl text-foreground">
              How can I help?
            </h1>
            <p className="mt-3 max-w-sm text-[15px] leading-relaxed text-muted-foreground">
              Send a message to begin. Keep typing to steer the reply in real
              time while it streams.
            </p>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl pb-8">
            {turns.map((g) => (
              <Turn key={g.key} group={g} />
            ))}
          </div>
        )}
      </div>
      <Composer onSend={onSend} onStop={onStop} streaming={streaming} />
    </main>
  );
}
