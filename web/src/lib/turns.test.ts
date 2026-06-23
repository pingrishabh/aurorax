import { describe, it, expect } from "vitest";
import { groupTurns } from "./turns";
import type { Message } from "./types";

function msg(p: Partial<Message>): Message {
  return {
    id: "id",
    session_id: "s",
    role: "user",
    content: "",
    status: "complete",
    steered: false,
    turn_id: null,
    is_steer: false,
    created_at: "2026-01-01T00:00:00Z",
    ...p,
  };
}

describe("groupTurns", () => {
  it("groups a prompt and its reply by turn_id", () => {
    const u = msg({ id: "u", role: "user", turn_id: "a", content: "hello" });
    const a = msg({ id: "a", role: "assistant", turn_id: "a", content: "hi" });
    const turns = groupTurns([u, a]);
    expect(turns).toHaveLength(1);
    expect(turns[0].prompt?.id).toBe("u");
    expect(turns[0].reply?.id).toBe("a");
    expect(turns[0].steers).toHaveLength(0);
  });

  it("nests steers under the prompt and keeps the reply available", () => {
    const u = msg({ id: "u", role: "user", turn_id: "a" });
    const a = msg({ id: "a", role: "assistant", turn_id: "a", steered: true });
    const s1 = msg({ id: "s1", role: "user", turn_id: "a", is_steer: true });
    const s2 = msg({ id: "s2", role: "user", turn_id: "a", is_steer: true });
    const turns = groupTurns([u, a, s1, s2]);
    expect(turns).toHaveLength(1);
    expect(turns[0].prompt?.id).toBe("u");
    expect(turns[0].steers.map((s) => s.id)).toEqual(["s1", "s2"]);
    expect(turns[0].reply?.id).toBe("a");
  });

  it("keeps turns in first-seen order", () => {
    const m = [
      msg({ id: "u1", turn_id: "a1" }),
      msg({ id: "a1", role: "assistant", turn_id: "a1" }),
      msg({ id: "u2", turn_id: "a2" }),
      msg({ id: "a2", role: "assistant", turn_id: "a2" }),
    ];
    expect(groupTurns(m).map((t) => t.key)).toEqual(["a1", "a2"]);
  });

  it("falls back to message id when turn_id is null", () => {
    const turns = groupTurns([msg({ id: "u", turn_id: null })]);
    expect(turns).toHaveLength(1);
    expect(turns[0].key).toBe("u");
    expect(turns[0].prompt?.id).toBe("u");
  });

  it("handles an empty list", () => {
    expect(groupTurns([])).toEqual([]);
  });
});
