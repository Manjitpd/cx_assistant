"""Server-side guardrails override an overconfident model."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.enums import ConversationStatus, MessageAuthor, OrderStatus
from app.schemas.conversation import (
    BrandSummary,
    ConversationDetail,
    CustomerSummary,
    MessageRead,
    OrderSummary,
)
from app.schemas.generation import EvidenceStatus
from app.schemas.retrieval import RetrievedKnowledge
from app.services.generation import generate_reply

REFUND_7 = "Refunds are permitted within 7 days of delivery."
REFUND_30 = "Refunds are permitted within 30 days of delivery."
SHIPPING = "Standard delivery takes 4 to 7 business days and costs $5."
OUTSIDE = "I received this 20 days ago. Can I get a refund?"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


class Scripted:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    async def generate_json(self, *, messages, json_schema):
        self.calls += 1
        return self.payload


def days_ago(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def thread(
    *,
    brand: str = "AquaPure",
    status: OrderStatus = OrderStatus.DELIVERED,
    delivered_at: datetime | None = None,
    body: str,
) -> ConversationDetail:
    created = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return ConversationDetail(
        id=uuid4(),
        subject="Refund question",
        status=ConversationStatus.OPEN,
        updated_at=created,
        created_at=created,
        brand=BrandSummary(id=uuid4(), name=brand, slug=brand.lower()),
        customer=CustomerSummary(id=uuid4(), full_name="Maya Chen", email="maya@example.com"),
        order=OrderSummary(
            id=uuid4(),
            order_number="AP-1042",
            product_name="AquaPure Classic Pitcher",
            status=status,
            total_cents=6400,
            currency="USD",
            placed_at=created,
            delivered_at=delivered_at,
        ),
        messages=[
            MessageRead(
                id=uuid4(),
                author_type=MessageAuthor.CUSTOMER,
                body=body,
                created_at=created,
            )
        ],
    )


def policy(content: str, category: str = "REFUND", title: str = "Refund policy") -> RetrievedKnowledge:
    return RetrievedKnowledge(
        knowledge_entry_id=uuid4(),
        title=title,
        category=category,
        content=content,
        score=0.4,
    )


def draft(text: str, knowledge_id) -> dict:
    return {
        "suggested_reply": text,
        "evidence_status": "SUPPORTED",
        "warning": None,
        "used_knowledge_ids": [str(knowledge_id)],
    }


def promises_refund(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "you can get a refund",
            "refund is approved",
            "i have already processed",
            "eligible for a refund",
        )
    )


async def main() -> None:
    seven = policy(REFUND_7)
    valid_provider = Scripted(
        draft("Yes, you can get a refund. I have already processed it.", seven.knowledge_entry_id)
    )
    valid = await generate_reply(
        thread(body="I received this 2 days ago. Can I get a refund?", delivered_at=days_ago(2)),
        "I received this 2 days ago. Can I get a refund?",
        [seven],
        provider=valid_provider,
    )
    expect(valid_provider.calls == 1, "valid refund skipped the model")
    expect(valid.evidence_status == EvidenceStatus.SUPPORTED, valid.evidence_status)
    expect("7 days" in valid.suggested_reply, valid.suggested_reply)
    expect("inside that window" in valid.suggested_reply, valid.suggested_reply)
    expect("does not show that the refund has already been issued" in valid.suggested_reply, valid.suggested_reply)
    expect(not promises_refund(valid.suggested_reply), valid.suggested_reply)

    outside_policy = policy(REFUND_7)
    outside_provider = Scripted(draft("Yes, you can get a refund.", outside_policy.knowledge_entry_id))
    outside = await generate_reply(
        thread(body=OUTSIDE),
        OUTSIDE,
        [outside_policy],
        provider=outside_provider,
    )
    expect(outside_provider.calls == 1, "outside-window refund skipped the model")
    expect(outside.evidence_status == EvidenceStatus.PARTIALLY_SUPPORTED, outside.evidence_status)
    expect("7 days" in outside.suggested_reply, outside.suggested_reply)
    expect("delivery date recorded" in outside.suggested_reply, outside.suggested_reply)
    expect("20 days ago" in outside.suggested_reply, outside.suggested_reply)
    expect(not promises_refund(outside.suggested_reply), outside.suggested_reply)
    expect("not recorded" in (outside.warning or ""), outside.warning)

    recorded = policy(REFUND_7)
    recorded_provider = Scripted(draft("Yes, you can get a refund.", recorded.knowledge_entry_id))
    recorded_reply = await generate_reply(
        thread(body=OUTSIDE, delivered_at=days_ago(20)),
        OUTSIDE,
        [recorded],
        provider=recorded_provider,
    )
    expect(recorded_reply.evidence_status == EvidenceStatus.SUPPORTED, recorded_reply.evidence_status)
    expect("outside that window" in recorded_reply.suggested_reply, recorded_reply.suggested_reply)
    expect("can't approve a refund" in recorded_reply.suggested_reply, recorded_reply.suggested_reply)
    expect(not promises_refund(recorded_reply.suggested_reply), recorded_reply.suggested_reply)

    shipping = policy(SHIPPING, "SHIPPING", "Shipping policy")
    missing_refund = Scripted(draft("Yes, you can get a refund within 14 days.", shipping.knowledge_entry_id))
    unknown_refund = await generate_reply(
        thread(body="Can I get a refund?"),
        "Can I get a refund?",
        [shipping],
        provider=missing_refund,
    )
    expect(missing_refund.calls == 0, "unknown refund policy called the model")
    expect(unknown_refund.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, unknown_refund.evidence_status)
    expect("can't confirm a refund" in unknown_refund.suggested_reply, unknown_refund.suggested_reply)
    expect("$5" not in unknown_refund.suggested_reply, unknown_refund.suggested_reply)
    expect("14" not in unknown_refund.suggested_reply, unknown_refund.suggested_reply)
    expect("Human review is required" in (unknown_refund.warning or ""), unknown_refund.warning)

    refund_only = policy(REFUND_7)
    missing_shipping = Scripted(draft("It ships in 2 days and costs $4.95.", refund_only.knowledge_entry_id))
    unknown_shipping = await generate_reply(
        thread(body="How long does shipping take and what does it cost?"),
        "How long does shipping take and what does it cost?",
        [refund_only],
        provider=missing_shipping,
    )
    expect(missing_shipping.calls == 0, "unknown shipping policy called the model")
    expect(unknown_shipping.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, unknown_shipping.evidence_status)
    expect("can't confirm" in unknown_shipping.suggested_reply, unknown_shipping.suggested_reply)
    expect("7 days" not in unknown_shipping.suggested_reply, unknown_shipping.suggested_reply)
    expect("$" not in unknown_shipping.suggested_reply, unknown_shipping.suggested_reply)

    broken_policy = policy(REFUND_7)
    broken_provider = Scripted(
        draft(
            "Broken products are an exception, so you can get a refund.",
            broken_policy.knowledge_entry_id,
        )
    )
    broken_message = "The product arrived broken. I received it 20 days ago. Can I get a refund?"
    broken = await generate_reply(
        thread(body=broken_message),
        broken_message,
        [broken_policy],
        provider=broken_provider,
    )
    expect(broken_provider.calls == 1, "broken product skipped the model")
    expect(broken.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, broken.evidence_status)
    expect("do not describe an exception" in broken.suggested_reply, broken.suggested_reply)
    expect("are an exception" not in broken.suggested_reply.lower(), broken.suggested_reply)
    expect(not promises_refund(broken.suggested_reply), broken.suggested_reply)
    expect("broken product" in (broken.warning or ""), broken.warning)

    status_policy = policy(REFUND_7)
    status_provider = Scripted(
        draft("Yes, your refund has already been processed.", status_policy.knowledge_entry_id)
    )
    status_message = "Has my refund already been issued?"
    status = await generate_reply(
        thread(body=status_message, status=OrderStatus.SHIPPED),
        status_message,
        [status_policy],
        provider=status_provider,
    )
    expect(status_provider.calls == 0, "unknown order action called the model")
    expect(status.evidence_status == EvidenceStatus.INSUFFICIENT_INFORMATION, status.evidence_status)
    expect("shipped" in status.suggested_reply, status.suggested_reply)
    expect("does not show" in status.suggested_reply, status.suggested_reply)
    expect("already been processed" not in status.suggested_reply.lower(), status.suggested_reply)

    aqua = policy(REFUND_7)
    tempted = Scripted(
        draft(
            "GlowNest accepts returns for 60 days and refunds shipping.",
            aqua.knowledge_entry_id,
        )
    )
    brand = await generate_reply(
        thread(body="Can I get a refund?"),
        "Can I get a refund?",
        [aqua],
        provider=tempted,
    )
    expect(tempted.calls == 1, "brand temptation skipped the model")
    expect(brand.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, brand.evidence_status)
    expect("GlowNest" not in brand.suggested_reply, brand.suggested_reply)
    expect("60" not in brand.suggested_reply, brand.suggested_reply)
    expect(not promises_refund(brand.suggested_reply), brand.suggested_reply)

    short = policy(REFUND_7, title="Short refund window")
    long = policy(REFUND_30, title="Long refund window")
    conflict_provider = Scripted(draft("Yes, you can get a refund within 30 days.", short.knowledge_entry_id))
    conflict = await generate_reply(
        thread(body="Can I get a refund?"),
        "Can I get a refund?",
        [short, long],
        provider=conflict_provider,
    )
    expect(conflict_provider.calls == 1, "conflicting policies skipped the model")
    expect(conflict.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, conflict.evidence_status)
    expect("disagree" in conflict.suggested_reply, conflict.suggested_reply)
    expect("7 days" in conflict.suggested_reply and "30 days" in conflict.suggested_reply, conflict.suggested_reply)
    expect(not promises_refund(conflict.suggested_reply), conflict.suggested_reply)
    expect("7 days" in (conflict.warning or "") and "30 days" in (conflict.warning or ""), conflict.warning)

    mismatched = policy(REFUND_7)
    mismatch_provider = Scripted(draft("Yes, you can get a refund.", mismatched.knowledge_entry_id))
    mismatch_message = "I received this 3 days ago. Can I get a refund?"
    mismatch = await generate_reply(
        thread(body=mismatch_message, delivered_at=days_ago(20)),
        mismatch_message,
        [mismatched],
        provider=mismatch_provider,
    )
    expect(mismatch.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, mismatch.evidence_status)
    expect("disagree" in mismatch.suggested_reply, mismatch.suggested_reply)
    expect(not promises_refund(mismatch.suggested_reply), mismatch.suggested_reply)

    print("guardrail checks passed")


if __name__ == "__main__":
    asyncio.run(main())
