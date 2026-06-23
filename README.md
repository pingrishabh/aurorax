# Mock Chat

A ChatGPT-style mock chat that demonstrates three requirements, with the
*architecture* as the real deliverable. There is no real LLM; workers stream
canned text token by token.

- **You never wait for a reply.** Sending never blocks the input, and a message
  sent *while a reply is streaming* **steers it in real time**: the reply pauses
  to "think", then regenerates in the new direction with a `steered` badge.
- **Multiple chat sessions** in a sidebar, persisted in Postgres so they survive
  reload.
- **Horizontally scalable backend:** stateless API replicas behind a load
  balancer, an independently-scaled worker pool, Redis for coordination.

Stack: React + Vite + Tailwind + shadcn-style UI (dark theme per
[`DESIGN.md`](./DESIGN.md)) · FastAPI (Python) · Postgres + Redis · nginx.
Architecture and scaling details in [ARCHITECTURE.md](./ARCHITECTURE.md).

## Quick start

Requires Docker (Desktop running). One command:

```bash
docker compose up --build
```

Open **http://localhost:8080**. That is the entire setup. It brings up Postgres,
Redis, 3 API replicas, 3 workers, and nginx (serving the SPA + load-balancing
the API). Only port 8080 is published; if it is taken, run
`PORT=9090 docker compose up --build` and open that port instead.

## Try it (90-second tour)

1. **Stream**: send "Tell me about horizontal scaling" and watch it type out.
2. **Steer mid-stream**: *while it is typing*, send "make it a haiku" (or "in
   French", "shorter", "be a pirate"). It badges **steered**, pauses to think,
   and regenerates in the new direction. The input was never blocked.
3. **Stop**: send, then hit ■. Generation halts; the reply is tagged **stopped**.
4. **Reload mid-stream**: refresh while it types; it reconnects and catches up
   the partial reply.
5. **Sessions**: "New chat" in the sidebar; switch, rename, or delete via the ⋯
   menu. Open the URL in a second tab to see the same persisted chats.
6. **Scale out**: `docker compose ps` shows 3 api + 3 worker. Add more:
   ```bash
   docker compose up --build --scale api=5 --scale worker=8
   ```

## Tests

Backend (48 pytest, throwaway Postgres + Redis, one command):

```bash
docker compose -f docker-compose.test.yml up --build \
  --abort-on-container-exit --exit-code-from tests
```

Frontend (13 vitest, pure logic, no infra):

```bash
cd web && npm install && npm test
```

Coverage spans the good/bad/ugly/edge: session CRUD + validation, the
steer-vs-new gate (incl. 12 simultaneous sends), turn grouping,
generation/thinking/cancel/last-steer-wins, the pub/sub multiplex hub + draft
buffer, and fault tolerance (outage durability, `XAUTOCLAIM` reclaim,
persist-then-ack, dead-lettering). The frontend tests cover turn grouping
(`lib/turns.ts`) and the SSE reducer (`lib/stream.ts`).

## Layout

```
server/                  # one Python package, two entrypoints
  app/main.py            #   api   : FastAPI REST + SSE (stateless)
  app/worker.py          #   worker: Redis consumer-group generation loop
  app/db.py              #   async SQLAlchemy engine + schema
  app/models.py          #   sessions / messages (Postgres)
  app/redis_bus.py       #   stream/queue + channel + key builders
  app/sse_hub.py         #   per-process pub/sub multiplexer for SSE
  app/mockllm.py         #   canned content pools + steer keyword routing
  app/schemas.py         #   pydantic request/response shapes
  tests/                 #   pytest suite
web/                     # Vite + React + TS + Tailwind
  src/components/        #   Sidebar, ChatPane, Turn, Composer, Logo, ui/*
  src/hooks/useChat.ts   #   non-blocking send + live SSE state
  src/lib/stream.ts      #   SSE frame reducer (seq de-dup, steer, reset, done)
  src/lib/turns.ts       #   group a prompt + its steers + reply into one turn
nginx/nginx.conf         # load balancer + SPA host + SSE-safe proxy
docker-compose.yml       # postgres, redis, api×3, worker×3, web(nginx)
docker-compose.test.yml  # hermetic backend test run
DESIGN.md                # design system the UI follows (dark, warm-neutral, coral)
```

## How each requirement is met

| Requirement | Mechanism |
|---|---|
| Don't wait for the reply | `POST` returns `202` after enqueuing on a Redis Stream; the UI is optimistic and never disables input |
| Steer in real time | a message during generation is `RPUSH`ed to a durable `steerq:{reply}` list; the worker drains it and regenerates (survives a worker outage) |
| Multiple sessions, persisted | sidebar over `sessions` / `messages` tables in Postgres |
| Horizontal scale | stateless `api` behind nginx + queue-fed `worker` pool + Redis pub/sub token fan-out (no sticky sessions) |
| Postgres & Redis only | Postgres = durable history; Redis = work queue + token fan-out + durable steer/cancel + reconnect buffer (each structure justified in ARCHITECTURE.md) |

## Optional: local dev (hot reload, no image rebuilds)

Publish the datastores with the dev overlay (kept out of the main compose so the
single command never conflicts on host ports), then run the rest locally:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis

# api (in server/)
cd server && pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://chat:chat@localhost:5432/chat \
REDIS_URL=redis://localhost:6379/0 uvicorn app.main:app --port 8000

# worker (another shell, in server/)
DATABASE_URL=postgresql+asyncpg://chat:chat@localhost:5432/chat \
REDIS_URL=redis://localhost:6379/0 python -m app.worker

# web (another shell, in web/): proxies /api to the api above
cd web && npm install && VITE_API_TARGET=http://localhost:8000 npm run dev
```

## Notes

- SSE through nginx needs `proxy_buffering off` + HTTP/1.1 (set in `nginx/nginx.conf`).
- Steering routes by keyword: shorter / detailed / French / haiku / pirate /
  excited; anything else rotates to a different style so the change is visible.
- Timing and TTLs are tunable via env (`TOKEN_MIN_DELAY`, `TOKEN_MAX_DELAY`,
  `THINK_MIN_DELAY`, `THINK_MAX_DELAY`, `ACTIVE_TTL`); see `.env.example`.
- A fresh clone needs no migration (the schema is created on boot). If you
  *upgrade in place* across a schema change, reset the volume once:
  `docker compose down -v && docker compose up --build`.
