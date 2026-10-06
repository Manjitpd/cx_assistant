"""Draft generation stays on the server and is not marked sent."""

import asyncio
import re
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.api.generation import post_generate_reply
from app.core.database import SessionLocal
from app.core.event_loop import loop_factory
from app.models import AIGenerationLog, Brand, Conversation, Customer, Message, Order
from app.models.enums import ConversationStatus, MessageAuthor
from app.schemas.generation import EvidenceStatus, GenerateReplyRequest
from app.services.ai_provider import HTTP_WARNING, TIMEOUT_WARNING, ProviderError
from app.services.generation import generate_conversation_reply

UNRELATED = "The xylophone metronome needs a rehearsal stand."


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


class RecordingProvider:
    def __init__(self, payload: dict | Exception) -> None:
        self.payload = payload
        self.calls = 0
        self.messages = None

    async def generate_json(self, *, messages, json_schema):
        self.calls += 1
        self.messages = messages
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def cite_retrieved(messages: list[dict[str, str]]) -> dict:
    content = messages[-1]["content"]
    match = re.search(r"id: ([0-9a-f-]{36})", content)
    policy = re.search(r"content: (.+)", content)
    expect(match is not None and policy is not None, "prompt did not include a retrieved policy")
    sentence = policy.group(1).split(".")[0].strip()
    expect(bool(sentence), "retrieved policy had no sentence")
    return {
        "suggested_reply": f"{sentence}.",
        "evidence_status": "supported",
        "warning": None,
        "used_knowledge_ids": [match.group(1)],
    }


class CitingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_json(self, *, messages, json_schema):
        self.calls += 1
        return cite_retrieved(messages)


async def message_count(session, conversation_id) -> int:
    count = await session.scalar(
        select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id)
    )
    return int(count or 0)


async def knowledge_ids(session, brand_id) -> set[str]:
    from app.models import KnowledgeBaseEntry

    rows = await session.scalars(
        select(KnowledgeBaseEntry.id).where(KnowledgeBaseEntry.brand_id == brand_id)
    )
    return {str(item) for item in rows}


async def add_thread(session, *, brand, customer, order, body: str, author: MessageAuthor) -> Conversation:
    conversation = Conversation(
        brand_id=brand.id,
        customer_id=customer.id,
        order_id=order.id,
        subject="Temporary generation check",
        status=ConversationStatus.OPEN,
    )
    session.add(conversation)
    await session.flush()
    session.add(
        Message(
            brand_id=brand.id,
            conversation_id=conversation.id,
            author_type=author,
            body=body,
        )
    )
    await session.commit()
    return conversation


async def remove_thread(session, conversation_id) -> None:
    await session.execute(delete(AIGenerationLog).where(AIGenerationLog.conversation_id == conversation_id))
    await session.execute(delete(Message).where(Message.conversation_id == conversation_id))
    await session.execute(delete(Conversation).where(Conversation.id == conversation_id))
    await session.commit()


async def main() -> None:
    created_logs: list = []
    async with SessionLocal() as session:
        aqua = await session.scalar(select(Brand).where(Brand.slug == "aquapure"))
        glow = await session.scalar(select(Brand).where(Brand.slug == "glownest"))
        expect(aqua is not None and glow is not None, "seed brands missing")
        aqua_ids = await knowledge_ids(session, aqua.id)
        glow_ids = await knowledge_ids(session, glow.id)
        thread = await session.scalar(
            select(Conversation).where(
                Conversation.brand_id == aqua.id,
                Conversation.subject.contains("AP-1042"),
            )
        )
        expect(thread is not None, "AquaPure conversation missing")
        before = await message_count(session, thread.id)
        customer = await session.scalar(select(Customer).where(Customer.brand_id == aqua.id).limit(1))
        order = await session.scalar(
            select(Order).where(Order.brand_id == aqua.id, Order.customer_id == customer.id).limit(1)
        )

        citing = CitingProvider()
        draft = await post_generate_reply(
            thread.id,
            payload=GenerateReplyRequest(brand_id=glow.id),
            brand_id=glow.id,
            session=session,
            provider=citing,
        )
        created_logs.append(draft.generation_id)
        expect(citing.calls == 1, "supported draft did not call the provider")
        expect(draft.evidence_status == EvidenceStatus.SUPPORTED, draft.evidence_status)
        expect(draft.warning is None, draft.warning)
        expect(draft.retrieved_knowledge, "expected AquaPure knowledge")
        expect(
            {str(item.knowledge_entry_id) for item in draft.retrieved_knowledge} <= aqua_ids,
            draft.retrieved_knowledge,
        )
        expect(
            {str(item.knowledge_entry_id) for item in draft.retrieved_knowledge}.isdisjoint(glow_ids),
            "GlowNest knowledge was retrieved for AquaPure",
        )
        quoted = draft.suggested_reply.rstrip(".")
        expect(
            any(quoted in item.content for item in draft.retrieved_knowledge),
            draft.suggested_reply,
        )
        stored = await session.get(AIGenerationLog, draft.generation_id)
        expect(stored is not None, "generation log missing")
        expect(stored.brand_id == aqua.id, stored.brand_id)
        expect(stored.conversation_id == thread.id, stored.conversation_id)
        expect(stored.evidence_status == "SUPPORTED", stored.evidence_status)
        expect(stored.suggested_reply == draft.suggested_reply, "log reply differs")
        expect(await message_count(session, thread.id) == before, "draft created a message")

        for label, payload in (
            ("timeout", ProviderError(TIMEOUT_WARNING)),
            ("api", ProviderError(HTTP_WARNING)),
            ("invalid", {"suggested_reply": 5}),
        ):
            provider = RecordingProvider(payload)
            result = await generate_conversation_reply(
                session,
                thread.id,
                provider=provider,
                brand_id=glow.id,
            )
            created_logs.append(result.generation_id)
            expect(provider.calls == 1, f"{label} did not call the provider")
            expect(result.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, result)
            expect(result.warning, f"{label} missing warning")
            expect("30 days" not in result.suggested_reply, result.suggested_reply)
            expect(
                {str(item.knowledge_entry_id) for item in result.retrieved_knowledge} <= aqua_ids,
                result.retrieved_knowledge,
            )
            row = await session.get(AIGenerationLog, result.generation_id)
            expect(row is not None and row.brand_id == aqua.id, f"{label} log")
            expect(row.message_author_type == "CUSTOMER", row.message_author_type)

        expect(await message_count(session, thread.id) == before, "failure path sent a message")

        silent = RecordingProvider({})
        unrelated = await add_thread(
            session,
            brand=aqua,
            customer=customer,
            order=order,
            body=UNRELATED,
            author=MessageAuthor.CUSTOMER,
        )
        try:
            empty = await generate_conversation_reply(session, unrelated.id, provider=silent)
            created_logs.append(empty.generation_id)
            expect(silent.calls == 0, "empty retrieval called OpenRouter")
            expect(empty.retrieved_knowledge == [], empty.retrieved_knowledge)
            expect(empty.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, empty.evidence_status)
            expect("No relevant brand knowledge" in (empty.warning or ""), empty.warning)
            expect(await message_count(session, unrelated.id) == 1, "empty draft sent a message")
        finally:
            await remove_thread(session, unrelated.id)

        agent_only = await add_thread(
            session,
            brand=aqua,
            customer=customer,
            order=order,
            body="Agent note with no customer question.",
            author=MessageAuthor.AGENT,
        )
        try:
            try:
                await generate_conversation_reply(session, agent_only.id, provider=silent)
                raise SystemExit("missing customer message was accepted")
            except HTTPException as error:
                expect(error.status_code == 422, error.detail)
                expect(error.detail == "Conversation has no customer message", error.detail)
            logs = await session.scalar(
                select(func.count())
                .select_from(AIGenerationLog)
                .where(AIGenerationLog.conversation_id == agent_only.id)
            )
            expect(int(logs or 0) == 0, "missing customer message stored a log")
            expect(silent.calls == 0, "missing customer message called the provider")
        finally:
            await remove_thread(session, agent_only.id)

        try:
            await generate_conversation_reply(session, uuid4(), provider=silent)
            raise SystemExit("unknown conversation was accepted")
        except HTTPException as error:
            expect(error.status_code == 404, error.detail)
            expect(error.detail == "Conversation not found", error.detail)
        expect(silent.calls == 0, "unknown conversation called the provider")

        await session.execute(delete(AIGenerationLog).where(AIGenerationLog.id.in_(created_logs)))
        await session.commit()

    print("generate-reply checks passed")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=loop_factory)
