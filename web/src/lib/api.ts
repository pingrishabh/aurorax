import type { Message, SendResult, Session } from "./types";

const j = { "Content-Type": "application/json" };

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${url} -> ${res.status}`);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listSessions: () => req<Session[]>("/api/sessions"),

  createSession: () =>
    req<Session>("/api/sessions", { method: "POST", headers: j, body: "{}" }),

  renameSession: (id: string, title: string) =>
    req<Session>(`/api/sessions/${id}`, {
      method: "PATCH",
      headers: j,
      body: JSON.stringify({ title }),
    }),

  deleteSession: (id: string) =>
    req<void>(`/api/sessions/${id}`, { method: "DELETE" }),

  listMessages: (id: string) => req<Message[]>(`/api/sessions/${id}/messages`),

  sendMessage: (id: string, content: string) =>
    req<SendResult>(`/api/sessions/${id}/messages`, {
      method: "POST",
      headers: j,
      body: JSON.stringify({ content }),
    }),

  cancel: (id: string) =>
    req<void>(`/api/sessions/${id}/cancel`, { method: "POST" }),
};
