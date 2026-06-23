export type Role = "user" | "assistant";
export type MessageStatus = "pending" | "streaming" | "complete" | "cancelled";

export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  session_id: string;
  role: Role;
  content: string;
  status: MessageStatus;
  steered: boolean;
  turn_id: string | null;
  is_steer: boolean;
  created_at: string;
}

export interface SendResult {
  steered: boolean;
  assistant_message_id: string | null;
  target_message_id: string | null;
}

// Frames pushed over SSE by the api (relayed from the worker via Redis).
export type StreamFrame =
  | { type: "token"; mid: string; text: string; seq: number }
  | { type: "catchup"; mid: string; text: string; seq: number }
  | { type: "steered"; mid: string }
  | { type: "reset"; mid: string }
  | { type: "done"; mid: string; status: MessageStatus; steered: boolean };
