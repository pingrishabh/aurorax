import type { Message } from "./types";

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
