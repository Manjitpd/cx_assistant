"""Manual agent replies show up immediately, survive a reload, and skip AI logs."""

import asyncio
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select

from app.core.database import SessionLocal, engine
from app.core.event_loop import loop_factory
from app.models import AIGenerationLog, Message

BASE = "http://127.0.0.1:8001"
AQUA = "5bd85ac5-bf77-57bc-adcf-986fafcb1659"


def call(
    method: str,
    path: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode()
    merged = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=merged)
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read()
            body = json.loads(raw) if raw else None
            return response.status, body
    except urllib.error.HTTPError as error:
        raw = error.read()
        body = json.loads(raw) if raw else None
        return error.code, body


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def matching(detail: dict, body: str) -> list[dict]:
    return [message for message in detail["messages"] if message["body"] == body]


async def generation_count(conversation_id: str) -> int:
    async with SessionLocal() as session:
        value = await session.scalar(
            select(func.count())
            .select_from(AIGenerationLog)
            .where(AIGenerationLog.conversation_id == UUID(conversation_id))
        )
        return int(value or 0)


async def remove_messages(message_ids: list[str]) -> None:
    if not message_ids:
        return
    async with SessionLocal() as session:
        await session.execute(
            delete(Message).where(Message.id.in_([UUID(message_id) for message_id in message_ids]))
        )
        await session.commit()


async def main() -> None:
    created: list[str] = []
    query = urllib.parse.urlencode({"brand_id": AQUA})
    try:
        status, conversations = call("GET", f"/api/conversations?{query}")
        expect(status == 200 and isinstance(conversations, list) and conversations, "could not open the inbox")
        conversation_id = conversations[0]["id"]

        status, opened = call("GET", f"/api/conversations/{conversation_id}?{query}")
        expect(status == 200 and isinstance(opened, dict), f"could not open the conversation: {status}")
        before = len(opened["messages"])
        logs_before = await generation_count(conversation_id)

        reply_path = f"/api/conversations/{conversation_id}/manual-reply?{query}"
        status, blank = call(
            "POST",
            reply_path,
            {"body": "   "},
            {"Idempotency-Key": str(uuid4())},
        )
        expect(status == 422, f"whitespace reply should be rejected, got {status} {blank}")

        status, empty = call(
            "POST",
            reply_path,
            {"body": ""},
            {"Idempotency-Key": str(uuid4())},
        )
        expect(status == 422, f"empty reply should be rejected, got {status} {empty}")

        status, missing_key = call("POST", reply_path, {"body": "This must not be stored."})
        expect(status == 422, f"missing idempotency key should be rejected, got {status} {missing_key}")

        status, unchanged = call("GET", f"/api/conversations/{conversation_id}?{query}")
        expect(
            status == 200 and len(unchanged["messages"]) == before,
            "rejected reply was stored",
        )

        body = f"Manual agent reply {uuid4()}"
        key = str(uuid4())
        status, sent = call("POST", reply_path, {"body": body}, {"Idempotency-Key": key})
        expect(status == 200 and isinstance(sent, dict), f"manual reply failed: {status} {sent}")
        sent_matches = matching(sent, body)
        expect(len(sent_matches) == 1, "sent reply missing from the immediate history")
        expect(sent_matches[0]["author_type"] == "AGENT", sent_matches[0])
        expect(len(sent["messages"]) == before + 1, "history did not grow by one")
        message_id = sent_matches[0]["id"]
        created.append(message_id)

        status, refreshed = call("GET", f"/api/conversations/{conversation_id}?{query}")
        expect(status == 200 and isinstance(refreshed, dict), f"refresh failed: {status}")
        refreshed_matches = matching(refreshed, body)
        expect(
            len(refreshed_matches) == 1 and refreshed_matches[0]["id"] == message_id,
            "reply missing after refresh",
        )
        expect(refreshed_matches[0]["author_type"] == "AGENT", refreshed_matches[0])

        logs_after = await generation_count(conversation_id)
        expect(
            logs_after == logs_before,
            f"manual reply created an AI generation record ({logs_before} -> {logs_after})",
        )

        status, replay = call(
            "POST",
            reply_path,
            {"body": f"{body} changed"},
            {"Idempotency-Key": key},
        )
        expect(status == 200 and isinstance(replay, dict), f"replay failed: {status} {replay}")
        expect(len(replay["messages"]) == before + 1, "replay inserted a duplicate message")
        expect(matching(replay, body)[0]["id"] == message_id, "replay did not return the original message")
        expect(not matching(replay, f"{body} changed"), "replay stored a different body")

        second_body = f"Second manual reply {uuid4()}"
        status, second = call(
            "POST",
            reply_path,
            {"body": second_body},
            {"Idempotency-Key": str(uuid4())},
        )
        expect(status == 200 and isinstance(second, dict), f"second reply failed: {status} {second}")
        second_matches = matching(second, second_body)
        expect(len(second_matches) == 1 and second_matches[0]["author_type"] == "AGENT", second)
        expect(len(second["messages"]) == before + 2, "a new key should store a new reply")
        created.append(second_matches[0]["id"])

        logs_final = await generation_count(conversation_id)
        expect(logs_final == logs_before, "a second manual reply created an AI generation record")
        print("manual reply checks passed")
        print(f"thread={conversation_id} stored={message_id}")
    finally:
        await remove_messages(created)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=loop_factory)
