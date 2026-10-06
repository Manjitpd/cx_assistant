"""Generation history stores the audit record and leaves credentials out."""

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.api.generation import get_generation_history
from app.core.database import SessionLocal, engine
from app.core.event_loop import loop_factory
from app.models import AIGenerationLog, Brand, Conversation, Customer, Message, Order
from app.models.enums import ConversationStatus, MessageAuthor
from app.schemas.generation import GenerationLogRead
from app.services.ai_provider import OpenRouterProvider, ProviderError
from app.services.approval import edit_generation
from app.services.generation import generate_conversation_reply

SECRET = "sk-live-do-not-store"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


class QuotingProvider:
    model_name = "openai/gpt-4o-mini"

    def __init__(self) -> None:
        self.calls = 0

    async def generate_json(self, *, messages, json_schema):
        self.calls += 1
        content = messages[-1]["content"]
        match = re.search(r"id: ([0-9a-f-]{36})", content)
        policy = re.search(r"content: (.+)", content)
        expect(match is not None and policy is not None, "prompt did not include retrieved policy")
        sentence = policy.group(1).split(".")[0].strip()
        return {
            "suggested_reply": f"{sentence}.",
            "evidence_status": "SUPPORTED",
            "warning": None,
            "used_knowledge_ids": [match.group(1)],
            "api_key": SECRET,
            "_audit": {
                "model": self.model_name,
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        }


class SecretFailure:
    model_name = "openai/gpt-4o-mini"

    async def generate_json(self, *, messages, json_schema):
        raise ProviderError(f"Authorization Bearer {SECRET} failed")


async def add_thread(session, *, brand, customer, order) -> tuple[Conversation, Message]:
    conversation = Conversation(
        brand_id=brand.id,
        customer_id=customer.id,
        order_id=order.id,
        subject="Temporary generation audit",
        status=ConversationStatus.OPEN,
    )
    session.add(conversation)
    await session.flush()
    message = Message(
        brand_id=brand.id,
        conversation_id=conversation.id,
        author_type=MessageAuthor.CUSTOMER,
        body="Can I return this defective pitcher?",
    )
    session.add(message)
    await session.commit()
    return conversation, message


async def remove_thread(session, conversation_id) -> None:
    await session.execute(delete(AIGenerationLog).where(AIGenerationLog.conversation_id == conversation_id))
    await session.execute(delete(Message).where(Message.conversation_id == conversation_id))
    await session.execute(delete(Conversation).where(Conversation.id == conversation_id))
    await session.commit()


def transport(url, payload, headers, timeout):
    return {
        "model": "openai/gpt-4o-mini",
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "suggested_reply": "Quoted from policy.",
                            "evidence_status": "SUPPORTED",
                            "warning": None,
                            "used_knowledge_ids": [],
                        }
                    )
                }
            }
        ],
    }


async def main() -> None:
    provider = OpenRouterProvider(
        api_key=SECRET,
        model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=5,
        app_name="Datastraw CX Assistant",
        transport=transport,
    )
    parsed = await provider.generate_json(messages=[{"role": "user", "content": "hi"}], json_schema={"type": "object"})
    audit_text = json.dumps(parsed["_audit"])
    expect(SECRET not in audit_text, audit_text)
    expect("Bearer" not in audit_text, audit_text)
    expect(parsed["_audit"]["prompt_tokens"] == 3, parsed["_audit"])
    expect(parsed["_audit"]["model"] == "openai/gpt-4o-mini", parsed["_audit"])

    conversation_id = None
    async with SessionLocal() as session:
        try:
            aqua = await session.scalar(select(Brand).where(Brand.slug == "aquapure"))
            glow = await session.scalar(select(Brand).where(Brand.slug == "glownest"))
            expect(aqua is not None and glow is not None, "seed brands missing")
            customer = await session.scalar(select(Customer).where(Customer.brand_id == aqua.id).limit(1))
            order = await session.scalar(
                select(Order).where(Order.brand_id == aqua.id, Order.customer_id == customer.id).limit(1)
            )
            expect(customer is not None and order is not None, "seed customer or order missing")
            conversation, message = await add_thread(session, brand=aqua, customer=customer, order=order)
            conversation_id = conversation.id
            customer_message_id = message.id
            aqua_id = aqua.id
            glow_id = glow.id

            quoting = QuotingProvider()
            created = await generate_conversation_reply(session, conversation_id, provider=quoting)
            expect(quoting.calls == 1, "audit generation did not call the provider")
            original = created.suggested_reply
            stored = await session.get(AIGenerationLog, created.generation_id)
            expect(stored is not None, "generation log missing")
            expect(stored.conversation_id == conversation_id, stored.conversation_id)
            expect(stored.customer_message_id == customer_message_id, stored.customer_message_id)
            expect(stored.brand_id == aqua_id, stored.brand_id)
            expect(stored.suggested_reply == original, "original response was not stored")
            expect(stored.edited_reply is None and stored.final_reply is None, "draft stored a later reply")
            expect(stored.model_name == "openai/gpt-4o-mini", stored.model_name)
            expect(stored.latency_ms is not None and stored.latency_ms >= 0, stored.latency_ms)
            expect(stored.prompt_tokens == 11, stored.prompt_tokens)
            expect(stored.completion_tokens == 7, stored.completion_tokens)
            expect(stored.total_tokens == 18, stored.total_tokens)
            expect(stored.error_detail is None, stored.error_detail)
            expect(stored.created_at is not None, "timestamp missing")
            expect(stored.retrieved_knowledge_ids, "retrieved knowledge ids missing")
            expect(stored.retrieved_context, "retrieved context missing")
            expect(
                any(original.rstrip(".") in item["content"] for item in stored.retrieved_context),
                stored.retrieved_context,
            )
            expect(SECRET not in json.dumps(stored.retrieved_context), "secret stored in retrieved context")

            failed = await generate_conversation_reply(session, conversation_id, provider=SecretFailure())
            failure = await session.get(AIGenerationLog, failed.generation_id)
            expect(failure is not None, "failure log missing")
            expect(failure.error_detail == "The reply provider returned an error. Human review is required.", failure.error_detail)
            expect(SECRET not in (failure.error_detail or ""), failure.error_detail)
            expect(SECRET not in (failure.warning or ""), failure.warning)
            expect(failure.suggested_reply != original, "failure overwrote the original draft row")
            expect(failure.model_name == "openai/gpt-4o-mini", failure.model_name)

            history = await get_generation_history(conversation_id, brand_id=aqua_id, session=session)
            expect(len(history) == 2, history)
            expect(history[0].id == failed.generation_id, "history is not newest first")
            rendered = json.dumps([GenerationLogRead.model_validate(row).model_dump(mode="json") for row in history])
            expect(SECRET not in rendered, "history response exposed a credential")
            expect("Bearer" not in rendered, rendered)
            expect("api_key" not in GenerationLogRead.model_fields, "history schema has an api key field")

            edited = "Edited by the agent for the audit test."
            state = await edit_generation(session, created.generation_id, edited)
            expect(state.suggested_reply == original, state.suggested_reply)
            expect(state.edited_reply == edited, state.edited_reply)
            await session.refresh(stored)
            expect(stored.suggested_reply == original, "edit overwrote the original AI response")
            expect(stored.edited_reply == edited, stored.edited_reply)

            try:
                await get_generation_history(conversation_id, brand_id=glow_id, session=session)
                raise SystemExit("cross-brand history was returned")
            except HTTPException as error:
                expect(error.status_code == 404, error.detail)

            print("generation log checks passed")
        finally:
            await session.rollback()
            if conversation_id is not None:
                await remove_thread(session, conversation_id)
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=loop_factory)
