import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { applyFrame, assistantBase } from "@/lib/stream";
import type { Message, Session, StreamFrame } from "@/lib/types";

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
      setMessages((prev) => applyFrame(prev, frame, nextSeq.current, sid));
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
