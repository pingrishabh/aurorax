import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Message, Session, StreamFrame } from "@/lib/types";

function assistantBase(mid: string, sid: string, content: string): Message {
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

export function useChat() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  // Per-message next-expected token index, so a reconnect's catch-up + live
  // tokens never double-apply.
  const nextSeq = useRef<Map<string, number>>(new Map());

  const refreshSessions = useCallback(async () => {
    setSessions(await api.listSessions());
  }, []);

  // Initial load: ensure there is at least one session.
  useEffect(() => {
    (async () => {
      let s = await api.listSessions();
      if (s.length === 0) s = [await api.createSession()];
      setSessions(s);
      setActiveId((cur) => cur ?? s[0]?.id ?? null);
    })();
  }, []);

  // Load history whenever the active session changes.
  useEffect(() => {
    if (!activeId) return;
    nextSeq.current = new Map();
    let cancelled = false;
    (async () => {
      const m = await api.listMessages(activeId);
      if (!cancelled) setMessages(m);
    })();
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  // Live stream for the active session (EventSource auto-reconnects + catches up).
  useEffect(() => {
    if (!activeId) return;
    const sid = activeId;
    const es = new EventSource(`/api/sessions/${sid}/stream`);

    es.onmessage = (ev) => {
      let frame: StreamFrame;
      try {
        frame = JSON.parse(ev.data);
      } catch {
        return;
      }
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.id === frame.mid);
        const patch = (p: Partial<Message>, base?: Message): Message[] => {
          if (idx === -1) return base ? [...prev, { ...base, ...p }] : prev;
          const copy = prev.slice();
          copy[idx] = { ...copy[idx], ...p };
          return copy;
        };
        switch (frame.type) {
          case "catchup":
            nextSeq.current.set(frame.mid, frame.seq);
            return patch(
              { content: frame.text, status: "streaming" },
              assistantBase(frame.mid, sid, frame.text)
            );
          case "token": {
            const expect = nextSeq.current.get(frame.mid) ?? 0;
            if (frame.seq < expect) return prev; // already applied
            nextSeq.current.set(frame.mid, frame.seq + 1);
            const existing = idx === -1 ? "" : prev[idx].content;
            return patch(
              { content: existing + frame.text, status: "streaming" },
              assistantBase(frame.mid, sid, frame.text)
            );
          }
          case "steered":
            return patch({ steered: true });
          case "reset":
            // Steering restarts the reply: clear the shown text so the
            // "Thinking…" placeholder appears until new tokens stream in.
            return patch({ content: "" });
          case "done":
            return patch({ status: frame.status, steered: frame.steered });
        }
      });
    };

    return () => es.close();
  }, [activeId]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!activeId) return;
      const sid = activeId;
      const tmpId = `tmp-${Date.now()}`;
      const optimistic: Message = {
        id: tmpId,
        session_id: sid,
        role: "user",
        content,
        status: "complete",
        steered: false,
        turn_id: null,
        is_steer: false,
        created_at: new Date().toISOString(),
      };
      setMessages((p) => [...p, optimistic]);

      const res = await api.sendMessage(sid, content);
      setMessages((p) => {
        // Backfill the user message with its turn grouping now that we know
        // whether it started a turn or steered an in-flight one.
        const turnId = res.steered ? res.target_message_id : res.assistant_message_id;
        const next = p.map((m) =>
          m.id === tmpId ? { ...m, turn_id: turnId, is_steer: res.steered } : m
        );
        // For a fresh turn, drop in the assistant placeholder (Thinking state).
        const mid = res.assistant_message_id;
        if (!res.steered && mid && !next.some((m) => m.id === mid)) {
          next.push({ ...assistantBase(mid, sid, ""), status: "pending" });
        }
        return next;
      });
      refreshSessions(); // title/order may have changed
    },
    [activeId, refreshSessions]
  );

  const cancelActive = useCallback(async () => {
    if (activeId) await api.cancel(activeId);
  }, [activeId]);

  const newSession = useCallback(async () => {
    const s = await api.createSession();
    setSessions((p) => [s, ...p]);
    setActiveId(s.id);
    setMessages([]);
  }, []);

  const renameSession = useCallback(
    async (id: string, title: string) => {
      await api.renameSession(id, title);
      refreshSessions();
    },
    [refreshSessions]
  );

  const deleteSession = useCallback(
    async (id: string) => {
      await api.deleteSession(id);
      const remaining = sessions.filter((s) => s.id !== id);
      setSessions(remaining);
      if (activeId === id) {
        if (remaining[0]) setActiveId(remaining[0].id);
        else await newSession();
      }
    },
    [sessions, activeId, newSession]
  );

  const isStreaming = messages.some(
    (m) => m.role === "assistant" && (m.status === "streaming" || m.status === "pending")
  );

  return {
    sessions,
    activeId,
    setActiveId,
    messages,
    isStreaming,
    sendMessage,
    cancelActive,
    newSession,
    renameSession,
    deleteSession,
  };
}
