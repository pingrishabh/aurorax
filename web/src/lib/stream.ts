import type { Message, StreamFrame } from "./types";

export function assistantBase(mid: string, sid: string, content: string): Message {
  return {
    id: mid,
    session_id: sid,
    role: "assistant",
    content,
    status: "streaming",
    steered: false,
    turn_id: mid,
    is_steer: false,
    created_at: new Date().toISOString(),
  };
}

// Pure reducer for an SSE frame. `nextSeq` tracks the next expected token index
// per message so a reconnect's catch-up + live tokens never double-apply.
export function applyFrame(
  prev: Message[],
  frame: StreamFrame,
  nextSeq: Map<string, number>,
  sid: string
): Message[] {
  const idx = prev.findIndex((m) => m.id === frame.mid);
  const patch = (p: Partial<Message>, base?: Message): Message[] => {
    if (idx === -1) return base ? [...prev, { ...base, ...p }] : prev;
    const copy = prev.slice();
    copy[idx] = { ...copy[idx], ...p };
    return copy;
  };

  switch (frame.type) {
    case "catchup":
      nextSeq.set(frame.mid, frame.seq);
      return patch(
        { content: frame.text, status: "streaming" },
        assistantBase(frame.mid, sid, frame.text)
      );
    case "token": {
      const expect = nextSeq.get(frame.mid) ?? 0;
      if (frame.seq < expect) return prev; // already applied (dedupe)
      nextSeq.set(frame.mid, frame.seq + 1);
      const existing = idx === -1 ? "" : prev[idx].content;
      return patch(
        { content: existing + frame.text, status: "streaming" },
        assistantBase(frame.mid, sid, frame.text)
      );
    }
    case "steered":
      return patch({ steered: true });
    case "reset":
      return patch({ content: "" });
    case "done":
      return patch({ status: frame.status, steered: frame.steered });
  }
}
