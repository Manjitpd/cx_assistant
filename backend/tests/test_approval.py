"""Approval keeps the original draft and sends it once."""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.api.generation import post_approve_generation, post_send_generation, put_generation
from app.core.database import SessionLocal
from app.core.event_loop import loop_factory
from app.models import AIGenerationLog, Brand, Conversation, Customer, Message, Order
from app.models.enums import ConversationStatus, MessageAuthor
from app.schemas.generation import GenerationEdit, GenerationStatus
from app.services.approval import approve_generation, edit_generation, send_generation

ORIGINAL = "Original AI text. AquaPure accepts unused items for 30 days."
EDITED = "Edited by the agent. The unused pitcher can be returned within 30 days."


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


async def agent_messages(session, conversation_id) -> list[Message]:
    rows = await session.scalars(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.author_type == MessageAuthor.AGENT,
        )
    )
    return list(rows)


async def main() -> None:
    async with SessionLocal() as session:
        aqua = await session.scalar(select(Brand).where(Brand.slug == "aquapure"))
        glow = await session.scalar(select(Brand).where(Brand.slug == "glownest"))
        expect(aqua is not None and glow is not None, "seed brands missing")
        customer = await session.scalar(select(Customer).where(Customer.brand_id == aqua.id).limit(1))
        order = await session.scalar(
            select(Order).where(Order.brand_id == aqua.id, Order.customer_id == customer.id).limit(1)
        )
        conversation = Conversation(
            brand_id=aqua.id,
            customer_id=customer.id,
            order_id=order.id,
            subject="Temporary approval check",
            status=ConversationStatus.OPEN,
        )
        session.add(conversation)
        await session.flush()
        customer_message = Message(
            brand_id=aqua.id,
            conversation_id=conversation.id,
            author_type=MessageAuthor.CUSTOMER,
            body="Can I return the pitcher?",
        )
        session.add(customer_message)
        await session.flush()
        log = AIGenerationLog(
            brand_id=aqua.id,
            conversation_id=conversation.id,
            customer_message_id=customer_message.id,
            message_author_type=MessageAuthor.CUSTOMER.value,
            suggested_reply=ORIGINAL,
            evidence_status="HUMAN_REVIEW_REQUIRED",
            warning="Human review is required.",
            retrieved_knowledge_ids=[],
            status=GenerationStatus.AI_GENERATED.value,
        )
        session.add(log)
        await session.commit()
        generation_id = log.id
        conversation_id = conversation.id
        aqua_id = aqua.id
        glow_id = glow.id

        try:
            blocked = None
            try:
                await send_generation(session, generation_id, brand_id=glow_id)
            except HTTPException as error:
                blocked = error
                await session.rollback()
            expect(blocked is not None and blocked.status_code == 409, blocked)
            expect(len(await agent_messages(session, conversation_id)) == 0, "unapproved send created a message")

            missing = None
            try:
                await approve_generation(session, uuid4())
            except HTTPException as error:
                missing = error
                await session.rollback()
            expect(missing is not None and missing.status_code == 404, missing)

            edited = await put_generation(
                generation_id,
                GenerationEdit(edited_reply=EDITED, brand_id=glow_id),
                brand_id=glow_id,
                session=session,
            )
            expect(edited.status == GenerationStatus.EDITED, edited.status)
            expect(edited.suggested_reply == ORIGINAL, edited.suggested_reply)
            expect(edited.edited_reply == EDITED, edited.edited_reply)
            expect(edited.final_reply is None, edited.final_reply)
            stored = await session.get(AIGenerationLog, generation_id)
            expect(stored.suggested_reply == ORIGINAL, "original AI response was overwritten")
            expect(stored.brand_id == aqua_id, stored.brand_id)

            approved = await post_approve_generation(generation_id, brand_id=glow_id, session=session)
            expect(approved.status == GenerationStatus.APPROVED, approved.status)
            expect(approved.suggested_reply == ORIGINAL, approved.suggested_reply)
            expect(len(await agent_messages(session, conversation_id)) == 0, "approve created a message")

            changed = await edit_generation(session, generation_id, EDITED + " Please use the prepaid label.")
            expect(changed.status == GenerationStatus.EDITED, changed.status)
            expect(changed.suggested_reply == ORIGINAL, "edit changed the original")
            refused = None
            try:
                await send_generation(session, generation_id)
            except HTTPException as error:
                refused = error
                await session.rollback()
            expect(refused is not None and refused.status_code == 409, refused)

            await approve_generation(session, generation_id)
            first = await post_send_generation(generation_id, brand_id=glow_id, session=session)
            sent_id = first.id
            sent_body = first.body
            sent_author = first.author_type
            second = await send_generation(session, generation_id, brand_id=glow_id)
            expect(sent_id == second.id, "retried send created another message")
            expect(sent_author == MessageAuthor.AGENT, sent_author)
            expect(sent_body == EDITED + " Please use the prepaid label.", sent_body)
            sent_rows = await agent_messages(session, conversation_id)
            expect(len(sent_rows) == 1, sent_rows)
            stored = await session.get(AIGenerationLog, generation_id)
            expect(stored.status == GenerationStatus.SENT.value, stored.status)
            expect(stored.suggested_reply == ORIGINAL, stored.suggested_reply)
            expect(stored.edited_reply == EDITED + " Please use the prepaid label.", stored.edited_reply)
            expect(stored.final_reply == sent_body, stored.final_reply)
            expect(stored.sent_message_id == sent_id, stored.sent_message_id)
            expect(stored.brand_id == aqua_id, stored.brand_id)
            expect(sent_rows[0].brand_id == aqua_id, sent_rows[0].brand_id)

            locked = None
            try:
                await edit_generation(session, generation_id, "This must not replace the original.")
            except HTTPException as error:
                locked = error
                await session.rollback()
            expect(locked is not None and locked.status_code == 409, locked)
            stored = await session.get(AIGenerationLog, generation_id)
            expect(stored.suggested_reply == ORIGINAL, stored.suggested_reply)
            expect(stored.final_reply == sent_body, stored.final_reply)
            expect(len(await agent_messages(session, conversation_id)) == 1, "edit after send created a message")
        finally:
            await session.rollback()
            await session.execute(delete(AIGenerationLog).where(AIGenerationLog.conversation_id == conversation_id))
            await session.execute(delete(Message).where(Message.conversation_id == conversation_id))
            await session.execute(delete(Conversation).where(Conversation.id == conversation_id))
            await session.commit()

    print("approval checks passed")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=loop_factory)
