# Mock Chat, steerable, multi-session, horizontally scalable

A ChatGPT-style mock chat UI that demonstrates three requirements:

- **You never wait for a reply.** Sending never blocks the input, and a message
  sent *while a reply is still streaming* **steers it in real time** (the answer
  changes direction and gets a `steered` badge).
- **Multiple chat sessions**, ChatGPT-style sidebar, persisted server-side so
  they survive reload.
- **Horizontally scalable backend**, stateless API replicas behind a load
  balancer, an independently-scaled worker pool, Redis for coordination. See
  [ARCHITECTURE.md](./ARCHITECTURE.md).

Stack: React + Vite + Tailwind + shadcn/ui (Cal.com design language) · FastAPI
(Python) · Postgres + Redis · nginx. There is no real LLM; workers stream canned
text token-by-token.

## Run it (one command)

Requires Docker Desktop running.

```bash
docker compose up --build
```

Then open **http://localhost:8080**.

This starts the full distributed topology: Postgres, Redis, **3× api**,
**3× worker**, and nginx serving the SPA + load-balancing the api replicas.

## Try the demo (smoke checklist)

1. **Stream**, send "Tell me about horizontal scaling." Watch it type out.
2. **Steer mid-stream**, *while it is still typing*, send "make it shorter" (or
   "in French", "as a haiku", "be a pirate"). The reply changes direction and
   shows a **steered** badge. Input was never blocked.
3. **Stop**, send a message, then hit the ■ Stop button. Generation halts and
   the message is tagged **stopped**.
4. **Reload mid-stream**, send a message and refresh the page while it types.
   It reconnects and catches up the partial reply (Postgres history + Redis
   draft buffer).
5. **Multiple sessions**, "New" in the sidebar; switch between chats; rename /
   delete via the ⋯ menu. Open http://localhost:8080 in a second tab to see the
   same persisted sessions.
6. **It's really distributed**, `docker compose ps` shows 3 api + 3 worker.
   Scale further:
   ```bash
   docker compose up --build --scale api=5 --scale worker=8
   ```

## Project layout

```
server/                 # Python package, one codebase, two entrypoints
  app/main.py           #   api  (FastAPI: REST + SSE)         [stateless]
  app/worker.py         #   worker (Redis consumer-group loop) [generation]
  app/db.py             #   async SQLAlchemy engine + schema
  app/models.py         #   sessions / messages (Postgres)
  app/redis_bus.py      #   queue, pub/sub channels, draft + active keys
  app/mockllm.py        #   canned content pools + steering routing
  app/schemas.py        #   pydantic request/response shapes
web/                    # Vite + React + TS + Tailwind + shadcn/ui
  src/hooks/useChat.ts  #   non-blocking send + SSE apply (seq de-dup)
  src/components/...     #   Sidebar, ChatPane, Composer, Message, ui/*
  DESIGN.md             #   Cal.com design notes (from `getdesign add cal`)
nginx/nginx.conf        # load balancer + static host + SSE-safe proxy
docker-compose.yml      # postgres, redis, api×3, worker×3, web(nginx)
```

## How the requirements are met (quick map)

| Requirement | Mechanism |
|---|---|
| Don't wait for the reply | `POST` returns `202` after enqueuing; UI is optimistic and never disables input |
| Steer in real time | new message during generation → `PUBLISH steer:{session}` → worker adapts the live stream |
| Multiple sessions, persisted | sidebar over `sessions`/`messages` tables in Postgres |
| Horizontal scale | stateless `api` behind nginx + queue-fed `worker` pool + Redis Pub/Sub fan-out (no sticky sessions) |
| Postgres & Redis only, justified | Postgres = durable history; Redis = queue + live fan-out + steer/cancel + reconnect buffer (see ARCHITECTURE.md) |

## Optional: local dev (without rebuilding images)

Run Postgres + Redis in Docker, the rest as local processes:

```bash
docker compose up -d postgres redis

# api (in server/)
cd server && pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://chat:chat@localhost:5432/chat \
REDIS_URL=redis://localhost:6379/0 \
uvicorn app.main:app --port 8000

# worker (another shell, in server/)
DATABASE_URL=postgresql+asyncpg://chat:chat@localhost:5432/chat \
REDIS_URL=redis://localhost:6379/0 \
python -m app.worker

# web (another shell, in web/), proxies /api to the api above
cd web && npm install && VITE_API_TARGET=http://localhost:8000 npm run dev
```

## Notes
- SSE through nginx needs `proxy_buffering off` + HTTP/1.1 (configured in
  `nginx/nginx.conf`).
- Steering routes by keyword: shorter / detailed / French / haiku / pirate /
  excited; anything else rotates to a different style so the change is visible.
- Token pacing and TTLs are tunable via env (`TOKEN_MIN_DELAY`,
  `TOKEN_MAX_DELAY`, `ACTIVE_TTL`), see `.env.example`.
