"""End-to-end support flow against the running API.

This drives the same HTTP calls the inbox uses. It does not click the page.
"""

import asyncio
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal, engine
from app.core.event_loop import loop_factory
from app.models import AIGenerationLog, Brand, Conversation, Customer, Message, Order
from app.models.enums import ConversationStatus, MessageAuthor
from app.services.ai_provider import ProviderError
from app.services.generation import generate_conversation_reply

BASE = "http://127.0.0.1:8001"
BROKEN = "My order was delivered but the bottle is broken. What can I do?"
MARKER = "ZX-POLICY-77"
NO_POLICY = "The xylophone metronome needs a rehearsal stand."
EDITED = "AquaPure can replace a defective unit after we confirm the order. This edited reply is the one that should be sent."


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def call(
    method: str,
    path: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60,
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode()
    merged = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=merged)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            body = json.loads(raw) if raw else None
            return response.status, body
    except urllib.error.HTTPError as error:
        raw = error.read()
        body = json.loads(raw) if raw else None
        return error.code, body


def query(brand_id: str) -> str:
    return urllib.parse.urlencode({"brand_id": brand_id})


class FailingProvider:
    model_name = "openai/gpt-4o-mini"

    async def generate_json(self, *, messages, json_schema):
        raise ProviderError("The reply provider timed out. Human review is required.")


def promises_refund(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "you can get a refund",
            "refund is approved",
            "eligible for a refund",
            "we can refund",
        )
    )


async def add_thread(session, *, brand, customer, order, subject: str) -> Conversation:
    conversation = Conversation(
        brand_id=brand.id,
        customer_id=customer.id,
        order_id=order.id,
        subject=subject,
        status=ConversationStatus.OPEN,
    )
    session.add(conversation)
    await session.flush()
    session.add(
        Message(
            brand_id=brand.id,
            conversation_id=conversation.id,
            author_type=MessageAuthor.CUSTOMER,
            body="Hello, I need help with this order.",
            )
    )
    await session.commit()
    return conversation


async def remove_thread(session, conversation_id) -> None:
    await session.execute(delete(AIGenerationLog).where(AIGenerationLog.conversation_id == conversation_id))
    await session.execute(delete(Message).where(Message.conversation_id == conversation_id))
    await session.execute(delete(Conversation).where(Conversation.id == conversation_id))
    await session.commit()


def ids_of(entries: list[dict]) -> set[str]:
    return {entry["id"] if "id" in entry else entry["knowledge_entry_id"] for entry in entries}


async def main() -> None:
    aqua_thread_id = None
    glow_thread_id = None
    original_refund = None
    refund_id = None
    aqua_query = ""
    async with SessionLocal() as session:
        try:
            status, health = call("GET", "/health")
            expect(status == 200 and health.get("database") == "ok", f"health: {status} {health}")

            status, brands = call("GET", "/api/brands")
            expect(status == 200, f"brands: {status} {brands}")
            by_name = {brand["name"]: brand for brand in brands}
            aqua = by_name["AquaPure"]
            glow = by_name["GlowNest"]
            aqua_query = query(aqua["id"])
            glow_query = query(glow["id"])

            status, aqua_knowledge = call("GET", f"/api/brands/{aqua['id']}/knowledge")
            status_g, glow_knowledge = call("GET", f"/api/brands/{glow['id']}/knowledge")
            expect(status == 200 and status_g == 200, "knowledge list failed")
            aqua_ids = {entry["id"] for entry in aqua_knowledge}
            glow_ids = {entry["id"] for entry in glow_knowledge}
            expect(aqua_ids.isdisjoint(glow_ids), "knowledge ids overlap")
            refund = next(entry for entry in aqua_knowledge if entry["category"] == "REFUND")
            refund_id = refund["id"]
            original_refund = {
                "title": refund["title"],
                "category": refund["category"],
                "content": refund["content"],
                "active": refund["active"],
            }

            status, aqua_threads = call("GET", f"/api/conversations?{aqua_query}")
            expect(status == 200 and aqua_threads, "AquaPure inbox did not open")
            expect(all(row["brand"]["id"] == aqua["id"] for row in aqua_threads), "AquaPure inbox leaked")
            leak = next(row for row in aqua_threads if "AP-1042" in row["subject"])
            status, opened = call("GET", f"/api/conversations/{leak['id']}?{aqua_query}")
            expect(status == 200 and opened["brand"]["name"] == "AquaPure", f"open AquaPure: {status}")
            print("1. opened AquaPure conversation", leak["id"])

            aqua_brand = await session.get(Brand, uuid.UUID(aqua["id"]))
            customer = await session.get(Customer, uuid.UUID(opened["customer"]["id"]))
            order = await session.get(Order, uuid.UUID(opened["order"]["id"]))
            thread = await add_thread(
                session,
                brand=aqua_brand,
                customer=customer,
                order=order,
                subject="E2E broken bottle",
            )
            aqua_thread_id = thread.id
            thread_query = f"/api/conversations/{aqua_thread_id}?{aqua_query}"

            status, sent_customer = call(
                "POST",
                f"/api/conversations/{aqua_thread_id}/messages?{aqua_query}",
                {"body": BROKEN},
            )
            expect(status == 200, f"customer message: {status} {sent_customer}")
            expect(sent_customer["messages"][-1]["body"] == BROKEN, sent_customer["messages"][-1])
            expect(sent_customer["messages"][-1]["author_type"] == "CUSTOMER", "customer author")
            print("2. customer message stored")
            print("3. agent reply uses the AI send path, separate from the customer composer")

            status, draft = call(
                "POST",
                f"/api/conversations/{aqua_thread_id}/generate-reply",
                None,
                timeout=90,
            )
            expect(status == 200, f"generate: {status} {draft}")
            retrieved = draft["retrieved_knowledge"]
            retrieved_ids = {item["knowledge_entry_id"] for item in retrieved}
            expect(retrieved_ids <= aqua_ids, f"non-AquaPure knowledge: {retrieved_ids - aqua_ids}")
            expect(retrieved_ids.isdisjoint(glow_ids), "GlowNest knowledge retrieved for AquaPure")
            expect(retrieved, "no knowledge retrieved for the broken-bottle question")
            expect(
                all(item["title"] and item["content"] and item["category"] for item in retrieved),
                retrieved,
            )
            print("4-6. generated reply; retrieved", len(retrieved), "AquaPure entries")
            print("    evidence", draft["evidence_status"])

            generation_id = draft["generation_id"]
            original = draft["suggested_reply"]
            status, edited = call(
                "PUT",
                f"/api/ai-generations/{generation_id}",
                {"edited_reply": EDITED},
            )
            expect(status == 200, f"edit: {status} {edited}")
            expect(edited["status"] == "EDITED", edited["status"])
            expect(edited["suggested_reply"] == original, "edit overwrote the original AI response")
            expect(edited["edited_reply"] == EDITED, edited["edited_reply"])
            print("7. edit saved; original preserved")

            status, approved = call("POST", f"/api/ai-generations/{generation_id}/approve")
            expect(status == 200 and approved["status"] == "APPROVED", f"approve: {status} {approved}")
            expect(approved["suggested_reply"] == original, "approve overwrote the original")
            status, during = call("GET", thread_query)
            expect(
                all(message["body"] != EDITED for message in during["messages"]),
                "approve created a sent message",
            )
            print("8. approved without sending")

            status, first_send = call("POST", f"/api/ai-generations/{generation_id}/send")
            expect(status == 200, f"send: {status} {first_send}")
            expect(first_send["author_type"] == "AGENT" and first_send["body"] == EDITED, first_send)
            sent_id = first_send["id"]
            status, after_send = call("GET", thread_query)
            expect(status == 200, "history reload failed")
            expect(after_send["messages"][-1]["id"] == sent_id, "sent reply missing from history")
            print("9-10. sent reply is the last history message")

            status, refreshed = call("GET", thread_query)
            expect(
                status == 200 and any(message["id"] == sent_id and message["body"] == EDITED for message in refreshed["messages"]),
                "sent reply missing after refresh",
            )
            print("11-12. refresh still shows the sent reply")

            status, second_send = call("POST", f"/api/ai-generations/{generation_id}/send")
            expect(status == 200 and second_send["id"] == sent_id, f"duplicate send: {status} {second_send}")
            status, after_duplicate = call("GET", thread_query)
            copies = [message for message in after_duplicate["messages"] if message["body"] == EDITED]
            expect(len(copies) == 1, f"duplicate send stored {len(copies)} copies")
            print("duplicate AI send returned the same message")

            manual_body = "Manual duplicate check for the broken bottle."
            manual_key = str(uuid.uuid4())
            status, manual = call(
                "POST",
                f"/api/conversations/{aqua_thread_id}/manual-reply?{aqua_query}",
                {"body": manual_body},
                {"Idempotency-Key": manual_key},
            )
            expect(status == 200, f"manual reply: {status} {manual}")
            status, manual_again = call(
                "POST",
                f"/api/conversations/{aqua_thread_id}/manual-reply?{aqua_query}",
                {"body": manual_body + " changed"},
                {"Idempotency-Key": manual_key},
            )
            expect(status == 200, f"manual replay: {status}")
            status, manual_read = call("GET", thread_query)
            manual_copies = [message for message in manual_read["messages"] if message["body"] == manual_body]
            expect(len(manual_copies) == 1, f"duplicate manual reply stored {len(manual_copies)} copies")
            expect(
                all(message["body"] != manual_body + " changed" for message in manual_read["messages"]),
                "idempotency key stored a second body",
            )
            print("duplicate manual reply kept a single message")

            updated_policy = dict(original_refund)
            updated_policy["content"] = (
                original_refund["content"]
                + f" {MARKER}: a refund still requires warehouse inspection and is not promised in chat."
            )
            status, saved = call(
                "PUT",
                f"/api/knowledge/{refund_id}?{aqua_query}",
                updated_policy,
            )
            expect(status == 200 and MARKER in saved["content"], f"policy update: {status} {saved}")
            print("13. AquaPure refund policy updated")

            status, asked = call(
                "POST",
                f"/api/conversations/{aqua_thread_id}/messages?{aqua_query}",
                {"body": f"What does {MARKER} say about a refund?"},
            )
            expect(status == 200, f"policy question: {status}")
            status, second = call(
                "POST",
                f"/api/conversations/{aqua_thread_id}/generate-reply",
                {"brand_id": glow["id"]},
                timeout=90,
            )
            expect(status == 200, f"second generate: {status} {second}")
            second_ids = {item["knowledge_entry_id"] for item in second["retrieved_knowledge"]}
            expect(second_ids <= aqua_ids, f"second draft left AquaPure: {second_ids - aqua_ids}")
            expect(
                any(MARKER in item["content"] for item in second["retrieved_knowledge"]),
                second["retrieved_knowledge"],
            )
            print("14-15. new refund policy was retrieved")

            glow_brand = await session.get(Brand, uuid.UUID(glow["id"]))
            glow_customer = await session.scalar(select(Customer).where(Customer.brand_id == glow_brand.id).limit(1))
            glow_order = await session.scalar(
                select(Order).where(Order.brand_id == glow_brand.id, Order.customer_id == glow_customer.id).limit(1)
            )
            glow_thread = await add_thread(
                session,
                brand=glow_brand,
                customer=glow_customer,
                order=glow_order,
                subject="E2E GlowNest isolation",
            )
            glow_thread_id = glow_thread.id
            status, glow_open = call("GET", f"/api/conversations/{glow_thread_id}?{glow_query}")
            expect(status == 200 and glow_open["brand"]["name"] == "GlowNest", f"open GlowNest: {status}")
            print("16. opened GlowNest conversation", glow_thread_id)

            status, glow_customer_message = call(
                "POST",
                f"/api/conversations/{glow_thread_id}/messages?{glow_query}",
                {"body": "Can I return this opened serum and get a refund?"},
            )
            expect(status == 200, f"GlowNest customer message: {status}")
            status, glow_draft = call(
                "POST",
                f"/api/conversations/{glow_thread_id}/generate-reply",
                {"brand_id": aqua["id"]},
                timeout=90,
            )
            expect(status == 200, f"GlowNest generate: {status} {glow_draft}")
            glow_retrieved = {item["knowledge_entry_id"] for item in glow_draft["retrieved_knowledge"]}
            expect(glow_retrieved <= glow_ids, f"AquaPure or foreign knowledge in GlowNest draft: {glow_retrieved - glow_ids}")
            expect(glow_retrieved.isdisjoint(aqua_ids), "AquaPure policies retrieved for GlowNest")
            expect(MARKER not in json.dumps(glow_draft["retrieved_knowledge"]), "AquaPure marker retrieved for GlowNest")
            print("17-18. GlowNest reply used only GlowNest knowledge")

            status, unknown = call(
                "POST",
                f"/api/conversations/{aqua_thread_id}/messages?{aqua_query}",
                {"body": NO_POLICY},
            )
            expect(status == 200, f"unknown question: {status}")
            status, unknown_draft = call(
                "POST",
                f"/api/conversations/{aqua_thread_id}/generate-reply",
                None,
                timeout=90,
            )
            expect(status == 200, f"unknown generate: {status} {unknown_draft}")
            expect(unknown_draft["retrieved_knowledge"] == [], unknown_draft["retrieved_knowledge"])
            expect(unknown_draft["evidence_status"] == "HUMAN_REVIEW_REQUIRED", unknown_draft["evidence_status"])
            expect(not promises_refund(unknown_draft["suggested_reply"]), unknown_draft["suggested_reply"])
            expect("30 days" not in unknown_draft["suggested_reply"], unknown_draft["suggested_reply"])
            expect("60 days" not in unknown_draft["suggested_reply"], unknown_draft["suggested_reply"])
            print("19-20. missing policy returned human review without an invented answer")

            status, covered = call(
                "POST",
                f"/api/conversations/{aqua_thread_id}/messages?{aqua_query}",
                {"body": "Can I return this defective pitcher?"},
            )
            expect(status == 200, f"failure setup message: {status} {covered}")
            before_messages = await session.scalar(
                select(func.count()).select_from(Message).where(Message.conversation_id == aqua_thread_id)
            )
            failure = await generate_conversation_reply(
                session,
                aqua_thread_id,
                provider=FailingProvider(),
            )
            after_messages = await session.scalar(
                select(func.count()).select_from(Message).where(Message.conversation_id == aqua_thread_id)
            )
            expect(failure.evidence_status.value == "HUMAN_REVIEW_REQUIRED", failure.evidence_status)
            expect(failure.warning, "provider failure had no warning")
            expect("timed out" in failure.warning.lower(), failure.warning)
            expect(after_messages == before_messages, "provider failure created a message")
            expect(not promises_refund(failure.suggested_reply), failure.suggested_reply)
            print("21-22. provider failure stayed a review draft and did not send")

            status, stolen = call("GET", f"/api/knowledge/{refund_id}?{glow_query}")
            expect(status == 404, f"cross-brand read: {status} {stolen}")
            status, tampered = call(
                "PUT",
                f"/api/knowledge/{refund_id}?{glow_query}",
                {
                    "title": "Stolen refund policy",
                    "category": "REFUND",
                    "content": "GlowNest rewrote the AquaPure refund policy.",
                    "active": True,
                    "brand_id": glow["id"],
                },
            )
            expect(status == 404, f"cross-brand write: {status} {tampered}")
            status, reread = call("GET", f"/api/knowledge/{refund_id}?{aqua_query}")
            expect(status == 200 and MARKER in reread["content"], "cross-brand write changed the policy")
            expect(reread["title"] == original_refund["title"], reread["title"])
            print("23-24. modified brand id was rejected and the policy stayed unchanged")

            print("e2e flow checks passed")
        finally:
            if refund_id and original_refund:
                status, restored = call(
                    "PUT",
                    f"/api/knowledge/{refund_id}?{aqua_query}",
                    original_refund,
                )
                if status != 200 or restored.get("content") != original_refund["content"]:
                    print(f"FAILED to restore refund policy: {status} {restored}")
                else:
                    print("restored AquaPure refund policy")
            await session.rollback()
            if aqua_thread_id is not None:
                await remove_thread(session, aqua_thread_id)
            if glow_thread_id is not None:
                await remove_thread(session, glow_thread_id)
            await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main(), loop_factory=loop_factory)
    except HTTPException as error:
        raise SystemExit(f"{error.status_code} {error.detail}") from error
