import { describe, it, expect, beforeEach } from "vitest";
import { applyFrame, assistantBase } from "./stream";
import type { Message } from "./types";

const SID = "sess";
let seq: Map<string, number>;

beforeEach(() => {
  seq = new Map();
});

function asst(content: string, extra: Partial<Message> = {}): Message {
  return { ...assistantBase("m1", SID, content), ...extra };
}

describe("applyFrame", () => {
  it("appends a token and advances the expected seq", () => {
    let msgs: Message[] = [asst("")];
    msgs = applyFrame(msgs, { type: "token", mid: "m1", text: "Hello", seq: 0 }, seq, SID);
    expect(msgs[0].content).toBe("Hello");
    expect(seq.get("m1")).toBe(1);
    msgs = applyFrame(msgs, { type: "token", mid: "m1", text: " world", seq: 1 }, seq, SID);
    expect(msgs[0].content).toBe("Hello world");
  });

  it("creates the assistant message if a token arrives before the placeholder", () => {
    const msgs = applyFrame([], { type: "token", mid: "m1", text: "hi", seq: 0 }, seq, SID);
    expect(msgs).toHaveLength(1);
    expect(msgs[0]).toMatchObject({ id: "m1", role: "assistant", turn_id: "m1", content: "hi" });
  });

  it("ignores a duplicate/old token (seq < expected)", () => {
    let msgs: Message[] = [asst("")];
    msgs = applyFrame(msgs, { type: "token", mid: "m1", text: "A", seq: 0 }, seq, SID);
    msgs = applyFrame(msgs, { type: "token", mid: "m1", text: "B", seq: 1 }, seq, SID);
    msgs = applyFrame(msgs, { type: "token", mid: "m1", text: "A", seq: 0 }, seq, SID);
    expect(msgs[0].content).toBe("AB"); // re-delivered seq 0 dropped
  });

  it("catchup replaces content, resets seq, and de-dupes the overlap", () => {
    let msgs: Message[] = [asst("stale")];
    msgs = applyFrame(msgs, { type: "catchup", mid: "m1", text: "caught up", seq: 5 }, seq, SID);
    expect(msgs[0].content).toBe("caught up");
    expect(seq.get("m1")).toBe(5);
    // live token with the next seq appends
    msgs = applyFrame(msgs, { type: "token", mid: "m1", text: "!", seq: 5 }, seq, SID);
    expect(msgs[0].content).toBe("caught up!");
    // overlapping pre-catchup token is de-duped
    msgs = applyFrame(msgs, { type: "token", mid: "m1", text: "X", seq: 4 }, seq, SID);
    expect(msgs[0].content).toBe("caught up!");
  });

  it("marks steered", () => {
    const msgs = applyFrame([asst("hi")], { type: "steered", mid: "m1" }, seq, SID);
    expect(msgs[0].steered).toBe(true);
  });

  it("reset clears content (back to a Thinking state)", () => {
    const msgs = applyFrame([asst("default reply so far")], { type: "reset", mid: "m1" }, seq, SID);
    expect(msgs[0].content).toBe("");
  });

  it("done sets final status and steered flag", () => {
    const msgs = applyFrame(
      [asst("done text")],
      { type: "done", mid: "m1", status: "complete", steered: true },
      seq,
      SID
    );
    expect(msgs[0]).toMatchObject({ status: "complete", steered: true });
  });

  it("ignores a control frame for an unknown message", () => {
    expect(applyFrame([], { type: "steered", mid: "ghost" }, seq, SID)).toEqual([]);
  });
});
