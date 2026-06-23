# Architecture

A mock ChatGPT-style app built to demonstrate three things: **non-blocking,
steerable replies**, **multiple persisted sessions**, and a backend that
**scales horizontally**. There is no real LLM — workers stream canned prose
token-by-token — but the *system* around it is the real, scalable design.

## Topology

```
                    ┌──────────────────────────┐
   Browser  ───────►│        nginx :8080       │   load balancer + static host
   (SPA, SSE)       │  serves SPA, proxies /api │   (single published port)
                    └─────────────┬────────────┘
                                  │  /api  (round-robins via Docker DNS)
                ┌─────────────────┼─────────────────┐
                ▼                 ▼                 ▼
           ┌─────────┐       ┌─────────┐       ┌─────────┐
           │  api-1  │       │  api-2  │  ...  │  api-N  │   FastAPI, STATELESS
           └────┬────┘       └────┬────┘       └────┬────┘   (no sticky sessions)
                │  XADD job / PUBLISH steer|cancel / SUBSCRIBE tokens
                └─────────────────┼──────────────────┘
                                  ▼
                       ┌──────────────────────┐
                       │        Redis         │  queue + pub/sub + draft buffer
                       │  Streams  +  Pub/Sub │  + active-generation registry
                       └──────────┬───────────┘
                                  │  XREADGROUP (consumer group "workers")
                ┌─────────────────┼─────────────────┐
                ▼                 ▼                 ▼
           ┌─────────┐       ┌─────────┐       ┌─────────┐
           │worker-1 │       │worker-2 │  ...  │worker-M │   generation tier
           └────┬────┘       └────┬────┘       └────┬────┘   (no HTTP, no ports)
                └─────────────────┼──────────────────┘
                                  ▼  persist final message
                       ┌──────────────────────┐
                       │      Postgres        │  durable source of truth
                       │  sessions / messages │  (history, survives restart)
                       └──────────────────────┘
```

`api` and `worker` are the **same Python package** (`/server`) run as two
different commands. The web tier and generation tier scale **independently**.

## The two datastores (and why only these)

The brief restricts state to **Postgres and Redis only**, each used only with a
genuine reason. Here is the full accounting.

### Postgres — durable source of truth
Sessions and messages must survive reloads and restarts, be listable, and load
on demand when a chat is opened. That is a relational, persistent,
queryable workload — exactly what Redis is *not* for. Two tables:
`sessions` and `messages` (`models.py`).

### Redis — coordination layer
Each structure has one job:

| Structure | Key/Channel | Why it must exist |
|---|---|---|
| **Work queue** (Stream + consumer group) | `gen:requests`, group `workers` | Lets the api accept a message and return **202 instantly** (non-blocking send), and lets workers scale out with at-least-once delivery + crash recovery (`XAUTOCLAIM`). Decouples *ingest* from *generation*. |
| **Token fan-out** (Pub/Sub) | `tokens:{session}` | The browser's SSE socket sits on one *stateless* api replica; the worker generating tokens is a different process on a different host. Pub/Sub bridges them, so **no sticky sessions / LB affinity** are needed. This is the linchpin of a scalable stateless web tier. |
| **Steering** (durable LIST) | `steerq:{message}` | A mid-reply message must reach *whichever* worker generates the reply — but it may be issued while the reply is still **queued** (e.g. during a worker outage). A durable list survives until the worker drains it on pickup, so steers are never lost. The worker polls it each token (≈one token of latency). |
| **Cancel** (durable flag, TTL) | `cancel:{message}` | Same idea for the Stop button: a flag the worker polls, honoured even if set just before the job starts. |
| **Draft buffer** (string/hash, TTL) | `draft:{message}` | Holds the partial reply so a **reloaded / reconnecting** SSE client can catch up before subscribing live (Pub/Sub alone drops anything sent before you subscribe). |
| **Active-generation registry** (key, TTL+heartbeat) | `gen:active:{session}` | A `SET NX` here is the atomic gate that decides **steer-vs-new-turn** consistently across all api replicas. |

Nothing else is stored in Redis; all durable business data lives in Postgres.

## Request lifecycles

### Send (never blocks)
1. `POST /api/sessions/{sid}/messages` → write the user message to Postgres.
2. `SET gen:active:{sid} <new-id> NX EX 60` — one atomic gate:
   - **won** → create a `pending` assistant row, `XADD` a job, return `202 {assistant_message_id}`.
   - **lost** → a reply is in flight (or still queued) → `RPUSH steerq:{mid}` (durable), mark that reply `steered`, return `202 {steered:true}`.
3. The UI optimistically shows the user bubble and clears the composer. You can
   immediately type and send again.

### Generate (worker)
`XREADGROUP` a job → mark `streaming` → loop emitting canned tokens (randomised
30–120 ms): append to `draft`, heartbeat `gen:active`, `PUBLISH tokens`. Each
iteration first **drains `steerq` and checks `cancel`** (durable, so anything
issued while the job was queued is honoured on pickup). On **steer** → badge the
reply, emit a `reset` frame, pause ~1.5 s to "think", then regenerate from
scratch in the new keyword-routed style (shorter / detailed / French / haiku /
pirate …). On **cancel** → stop. On finish → persist the final text + status to
Postgres, publish `done`, delete the per-message keys + `gen:active`, `XACK`.

### Stream (SSE, reload-safe)
`GET /api/sessions/{sid}/stream` subscribes to `tokens:{sid}`, first replays the
current `draft` as a `catchup` frame, then relays live frames. Each token frame
carries a `seq`; the client uses it to de-duplicate the catch-up/live overlap.
A heartbeat comment every 15 s keeps the stream open through nginx.

## Horizontal scaling — the ways, and what we chose

**Ways to scale a chat backend horizontally:**
1. **Stateless app servers behind a load balancer** — add replicas, no per-node
   state. *(Used: `api` is stateless; nginx round-robins.)*
2. **Decouple slow work onto a queue + worker pool** — scale producers and
   consumers separately. *(Used: Redis Stream + consumer group; `worker` scales
   on its own.)*
3. **Shared coordination bus instead of node affinity** — any node can serve any
   connection because cross-node messaging goes through Redis Pub/Sub. *(Used:
   the SSE socket and the generating worker need not be co-located.)*
4. **Shared durable store, scaled on its own axis** — Postgres with connection
   pooling now; read replicas for history reads, or partition/shard by
   `session_id` later. *(Designed for: all access is by `session_id`.)*
5. **Scale the bus** — split the queue Redis from the pub/sub Redis, or move to
   Redis Cluster; pub/sub keys are already per-session so they shard cleanly.

**Why this composition works:** the web tier holds no state, so it scales by
adding `api` replicas; generation is queue-fed, so it scales by adding `worker`
replicas; and because tokens/steer/cancel travel over Redis Pub/Sub keyed by
session, **a request can be served by any api replica and generated by any
worker** — there is no affinity to break when you scale out. Run it:

```bash
docker compose up --build --scale api=5 --scale worker=8
```

## Resilience notes
- **At-least-once** delivery: jobs are `XACK`-ed only after handling; a crashed
  worker's un-acked jobs are reclaimed by another via `XAUTOCLAIM` (idle > 30 s).
- **Outage-durable control:** steer/cancel use durable Redis structures
  (`steerq:{mid}` list, `cancel:{mid}` flag) the worker drains on pickup — so a
  message sent in a session whose worker pool is *down* still queues its job
  **and** carries its steer, both applied when capacity returns. (Live token
  *delivery* still rides Pub/Sub, which is correct: there's nothing to deliver
  to until a client is connected.)
- **TTLs everywhere** on Redis coordination keys, so a crash can't wedge a
  session: the `gen:active` gate, `draft` buffer, and per-message control keys
  self-heal after `ACTIVE_TTL`.
- **Reload-safe** streaming via the draft buffer + `seq` de-dup.

## What's intentionally mocked / simplified
- No real model: `mockllm.py` streams canned text; "steering" maps keywords to a
  different style so the change is visible.
- Single anonymous user, no auth.
- Steering targets the one in-flight reply per session (the chosen "one evolving
  answer" semantic), not multiple concurrent replies.
- For a production system you'd add auth, request idempotency keys, structured
  logging/metrics, and split the queue vs pub/sub Redis instances.
