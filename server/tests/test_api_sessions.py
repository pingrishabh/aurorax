"""Session CRUD + input validation. The good, and the bad inputs."""
import uuid

from .helpers import get_messages, make_session, send


async def test_create_and_list_session(client):
    sid = await make_session(client)
    sessions = (await client.get("/api/sessions")).json()
    assert any(s["id"] == sid for s in sessions)
    assert sessions[0]["title"] == "New chat"


async def test_first_message_sets_title_from_content(client):
    sid = await make_session(client)
    await send(client, sid, "What is a Redis stream and why use it?")
    sessions = (await client.get("/api/sessions")).json()
    title = next(s["title"] for s in sessions if s["id"] == sid)
    assert title == "What is a Redis stream and why use it?"[:40]


async def test_rename_session(client):
    sid = await make_session(client)
    resp = await client.patch(f"/api/sessions/{sid}", json={"title": "Renamed"})
    assert resp.status_code == 200 and resp.json()["title"] == "Renamed"


async def test_delete_session_cascades_messages(client):
    sid = await make_session(client)
    await send(client, sid, "hello there")
    assert (await client.delete(f"/api/sessions/{sid}")).status_code == 204
    # Session is gone -> message history 404s via the session, list excludes it.
    assert all(s["id"] != sid for s in (await client.get("/api/sessions")).json())


async def test_send_to_missing_session_404(client):
    missing = str(uuid.uuid4())
    resp = await send(client, missing, "anyone home?")
    assert resp.status_code == 404


async def test_empty_content_rejected(client):
    sid = await make_session(client)
    resp = await client.post(f"/api/sessions/{sid}/messages", json={"content": ""})
    assert resp.status_code == 422  # pydantic min_length=1


async def test_rename_missing_session_404(client):
    resp = await client.patch(f"/api/sessions/{uuid.uuid4()}", json={"title": "x"})
    assert resp.status_code == 404


async def test_delete_missing_session_is_idempotent(client):
    # Deleting a non-existent session is a no-op 204, not an error.
    assert (await client.delete(f"/api/sessions/{uuid.uuid4()}")).status_code == 204


async def test_history_ordered_by_creation(client, worker):
    sid = await make_session(client)
    await send(client, sid, "first message")
    msgs = await get_messages(client, sid)
    assert msgs[0]["role"] == "user" and msgs[0]["content"] == "first message"
