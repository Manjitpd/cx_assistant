import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models import AIGenerationLog, Conversation, Message
from app.models.enums import MessageAuthor
from app.schemas.conversation import ConversationDetail
from app.schemas.generation import EvidenceStatus, GenerateReplyResponse, GeneratedReply, GenerationStatus
from app.schemas.retrieval import RetrievedKnowledge
from app.services.ai_provider import AIProvider, ProviderError, get_ai_provider
from app.services.guardrails import assess, assessment_reply, guard_reply
from app.services.retrieval import retrieve_knowledge

_SECRET = re.compile(r"bearer\s+\S+|sk-[A-Za-z0-9]|api[_-]?key", re.IGNORECASE)
_SAFE_PROVIDER_ERROR = "The reply provider returned an error. Human review is required."


@dataclass
class GenerationAudit:
    model_name: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    error_detail: str | None = None


def redact_secrets(value: str | None) -> str | None:
    if value is None:
        return None
    if _SECRET.search(value):
        return _SAFE_PROVIDER_ERROR
    cleaned = value.strip()
    return cleaned or None


def _clean_model(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()[:120]
    if not cleaned or _SECRET.search(cleaned):
        return None
    return cleaned


def _token(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if value < 0 or not float(value).is_integer():
        return None
    return int(value)


def _context_snapshot(knowledge: Sequence[RetrievedKnowledge]) -> list[dict]:
    snapshot = []
    for entry in knowledge:
        category = entry.category.value if hasattr(entry.category, "value") else str(entry.category)
        snapshot.append(
            {
                "knowledge_entry_id": str(entry.knowledge_entry_id),
                "title": entry.title,
                "category": category,
                "content": entry.content,
                "score": float(entry.score),
            }
        )
    return snapshot

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "suggested_reply": {"type": "string"},
        "evidence_status": {
            "type": "string",
            "enum": [
                "SUPPORTED",
                "PARTIALLY_SUPPORTED",
                "INSUFFICIENT_INFORMATION",
                "HUMAN_REVIEW_REQUIRED",
            ],
        },
        "warning": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "used_knowledge_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["suggested_reply", "evidence_status", "warning", "used_knowledge_ids"],
    "additionalProperties": False,
}

_SYSTEM_INSTRUCTIONS = """
You write a customer-support reply for one brand.
Retrieved knowledge is the only source of truth for policy claims.
The order block is the only source of truth for order facts.
Do not invent refund policies.
Do not invent return windows.
Do not promise compensation without evidence.
Do not invent order information.
Do not use knowledge from another brand.
Do not pretend information exists when it does not.
If the retrieved policies do not support the customer's request, write a short clarifying reply, set evidence_status to HUMAN_REVIEW_REQUIRED, and do not state a policy outcome.
Use SUPPORTED only when every policy claim is in the retrieved policies and every order claim is in the order record.
Use PARTIALLY_SUPPORTED when some of the request is supported and the rest is not.
Use INSUFFICIENT_INFORMATION when a required fact is missing.
Use HUMAN_REVIEW_REQUIRED when no relevant policy exists, policies conflict, or a person must decide.
Do not invent exceptions.
Do not say a refund, cancellation, label, or shipment has already happened unless that fact is in the order record.
used_knowledge_ids must contain only ids from the retrieved policies. Use an empty list when none apply.
Return only the JSON object described by the schema.
""".strip()


def _money(cents: int, currency: str) -> str:
    return f"{currency} {cents / 100:.2f}"


def _fallback_reply(brand_name: str) -> str:
    return (
        f"Thank you for writing to {brand_name}. I don't have a {brand_name} policy "
        "that covers this, so I can't confirm a return window, refund, shipping rule, "
        "cancellation, or any compensation. A teammate will review the conversation "
        "and follow up."
    )


def _failure_reply() -> str:
    return (
        "Thank you for your message. I couldn't prepare a policy-based reply just now, "
        "so a teammate needs to review this before anything is promised."
    )


def build_messages(
    conversation: ConversationDetail,
    latest_customer_message: str,
    retrieved_knowledge: Sequence[RetrievedKnowledge],
) -> list[dict[str, str]]:
    history_lines = []
    messages = conversation.messages[-12:]
    if len(conversation.messages) > len(messages):
        history_lines.append("Earlier messages omitted.")
    for message in messages:
        speaker = conversation.customer.full_name if message.author_type.value == "CUSTOMER" else "Agent"
        history_lines.append(
            f"{speaker} ({message.author_type.value}) at {message.created_at.isoformat()}: "
            f"{message.body[:1500]}"
        )
    history = "\n".join(history_lines) if history_lines else "No earlier messages."

    order = conversation.order
    policy_lines = []
    for entry in retrieved_knowledge:
        policy_lines.append(
            "\n".join(
                [
                    f"id: {entry.knowledge_entry_id}",
                    f"title: {entry.title}",
                    f"category: {entry.category.value}",
                    f"content: {entry.content[:4000]}",
                ]
            )
        )
    policies = "\n\n".join(policy_lines) if policy_lines else "None."

    user = "\n\n".join(
        [
            "Brand identity",
            f"name: {conversation.brand.name}",
            f"slug: {conversation.brand.slug}",
            "Conversation history",
            f"subject: {conversation.subject}",
            f"status: {conversation.status.value}",
            history,
            "Order information",
            f"order_number: {order.order_number}",
            f"product_name: {order.product_name}",
            f"status: {order.status.value}",
            f"total: {_money(order.total_cents, order.currency)}",
            f"placed_at: {order.placed_at.isoformat()}",
            (
                f"delivery_date: {order.delivered_at.isoformat()}"
                if order.delivered_at is not None
                else "delivery_date: not recorded"
            ),
            "Retrieved brand-specific policies",
            policies,
            "Latest customer message",
            latest_customer_message.strip(),
            "Strict instructions",
            "Answer only from the brand identity, conversation history, order information, "
            "and retrieved policies above. Retrieved knowledge is the source of truth for "
            "policy-related claims. If it does not support a claim, ask for review instead "
            "of filling the gap.",
        ]
    )
    return [
        {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": user},
    ]


def _needs_review(reply: str, warning: str, used_ids: list[UUID] | None = None) -> GeneratedReply:
    return GeneratedReply(
        suggested_reply=reply,
        evidence_status=EvidenceStatus.HUMAN_REVIEW_REQUIRED,
        warning=warning,
        used_knowledge_ids=used_ids or [],
    )


def _sanitize(
    raw: dict,
    *,
    allowed_ids: set[UUID],
    brand_name: str,
) -> GeneratedReply:
    try:
        draft = GeneratedReply.model_validate(raw)
    except ValidationError as error:
        raise ProviderError("The reply provider returned an invalid draft. Human review is required.") from error

    cited: list[UUID] = []
    rejected = False
    for knowledge_id in draft.used_knowledge_ids:
        if knowledge_id in allowed_ids and knowledge_id not in cited:
            cited.append(knowledge_id)
        else:
            rejected = True

    reply = draft.suggested_reply.strip()
    if not reply or rejected or (draft.evidence_status == EvidenceStatus.SUPPORTED and not cited):
        warning = draft.warning or "The draft was not supported by retrieved knowledge."
        if rejected:
            warning = "The draft cited knowledge that was not retrieved for this brand."
        return _needs_review(_fallback_reply(brand_name), warning)

    warning = (draft.warning or "").strip() or None
    if draft.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED and warning is None:
        warning = "Human review is required."
    return GeneratedReply(
        suggested_reply=reply,
        evidence_status=draft.evidence_status,
        warning=warning,
        used_knowledge_ids=cited,
    )


async def generate_reply(
    conversation: ConversationDetail,
    latest_customer_message: str,
    retrieved_knowledge: Sequence[RetrievedKnowledge],
    *,
    provider: AIProvider | None = None,
    audit: GenerationAudit | None = None,
) -> GeneratedReply:
    started = time.perf_counter()

    def finish(
        reply: GeneratedReply,
        *,
        error_detail: str | None = None,
        meta: dict | None = None,
        model_name: str | None = None,
    ) -> GeneratedReply:
        warning = redact_secrets(reply.warning)
        safe = reply if warning == reply.warning else reply.model_copy(update={"warning": warning})
        if audit is not None:
            audit.latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            audit.error_detail = redact_secrets(error_detail)
            chosen = _clean_model(meta.get("model") if meta else None) or _clean_model(model_name)
            if chosen:
                audit.model_name = chosen
            if meta:
                audit.prompt_tokens = _token(meta.get("prompt_tokens"))
                audit.completion_tokens = _token(meta.get("completion_tokens"))
                audit.total_tokens = _token(meta.get("total_tokens"))
        return safe

    detail = (
        conversation
        if isinstance(conversation, ConversationDetail)
        else ConversationDetail.model_validate(conversation)
    )
    message = latest_customer_message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Customer message must not be blank")

    if not retrieved_knowledge:
        return finish(
            _needs_review(
                _fallback_reply(detail.brand.name),
                "No relevant brand knowledge was retrieved. Human review is required.",
            )
        )

    preview = assess(
        customer_message=message,
        knowledge=retrieved_knowledge,
        order=detail.order,
        brand_name=detail.brand.name,
    )
    if preview.skip_model:
        return finish(assessment_reply(preview))

    messages = build_messages(detail, message, retrieved_knowledge)
    selected = provider or get_ai_provider()
    model_name = _clean_model(getattr(selected, "model_name", None))
    try:
        raw = await selected.generate_json(messages=messages, json_schema=REPLY_SCHEMA)
        meta = raw.pop("_audit", None) if isinstance(raw, dict) else None
        if not isinstance(meta, dict):
            meta = None
        draft = _sanitize(
            raw,
            allowed_ids={entry.knowledge_entry_id for entry in retrieved_knowledge},
            brand_name=detail.brand.name,
        )
    except ProviderError as error:
        safe_warning = redact_secrets(error.warning) or _SAFE_PROVIDER_ERROR
        return finish(
            _needs_review(_failure_reply(), safe_warning),
            error_detail=safe_warning,
            model_name=model_name,
        )
    return finish(
        guard_reply(
            draft,
            customer_message=message,
            knowledge=retrieved_knowledge,
            order=detail.order,
            brand_name=detail.brand.name,
        ),
        meta=meta,
        model_name=model_name,
    )


async def generate_conversation_reply(
    session: AsyncSession,
    conversation_id: UUID,
    *,
    provider: AIProvider | None = None,
    brand_id: UUID | None = None,
) -> GenerateReplyResponse:
    """Draft a reply for the conversation's own brand.

    ``brand_id`` is ignored. The conversation row selects the brand, the
    latest customer message selects the query, and retrieval uses only that
    pair. Nothing is marked sent.
    """
    del brand_id
    conversation = await _load_conversation(session, conversation_id)
    latest = _latest_customer_message(conversation)
    knowledge = await retrieve_knowledge(
        session,
        conversation_id=conversation.id,
        customer_message=latest.body,
    )
    audit = GenerationAudit()
    draft = await generate_reply(
        conversation,
        latest.body,
        knowledge,
        provider=provider,
        audit=audit,
    )
    log = AIGenerationLog(
        brand_id=conversation.brand_id,
        conversation_id=conversation.id,
        customer_message_id=latest.id,
        message_author_type=MessageAuthor.CUSTOMER.value,
        suggested_reply=draft.suggested_reply,
        evidence_status=draft.evidence_status.value,
        warning=draft.warning,
        error_detail=audit.error_detail,
        retrieved_knowledge_ids=[str(entry.knowledge_entry_id) for entry in knowledge],
        retrieved_context=_context_snapshot(knowledge),
        model_name=audit.model_name,
        latency_ms=audit.latency_ms,
        prompt_tokens=audit.prompt_tokens,
        completion_tokens=audit.completion_tokens,
        total_tokens=audit.total_tokens,
        status=GenerationStatus.AI_GENERATED.value,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return GenerateReplyResponse(
        suggested_reply=draft.suggested_reply,
        retrieved_knowledge=list(knowledge),
        evidence_status=draft.evidence_status,
        warning=draft.warning,
        generation_id=log.id,
        status=GenerationStatus.AI_GENERATED,
    )


async def list_generation_logs(
    session: AsyncSession,
    conversation_id: UUID,
    brand_id: UUID,
) -> list[AIGenerationLog]:
    """Return audit rows for one brand's conversation.

    A brand_id that does not own the conversation is a 404, so the lookup
    does not reveal that another brand's thread exists.
    """
    conversation = await session.scalar(
        select(Conversation.id).where(
            Conversation.id == conversation_id,
            Conversation.brand_id == brand_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = await session.scalars(
        select(AIGenerationLog)
        .where(
            AIGenerationLog.conversation_id == conversation_id,
            AIGenerationLog.brand_id == brand_id,
        )
        .order_by(AIGenerationLog.created_at.desc(), AIGenerationLog.id.desc())
    )
    return list(rows)


async def _load_conversation(session: AsyncSession, conversation_id: UUID) -> Conversation:
    conversation = await session.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(
            joinedload(Conversation.brand),
            joinedload(Conversation.customer),
            joinedload(Conversation.order),
            selectinload(Conversation.messages),
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _latest_customer_message(conversation: Conversation) -> Message:
    latest = next(
        (
            message
            for message in reversed(conversation.messages)
            if message.author_type == MessageAuthor.CUSTOMER
        ),
        None,
    )
    if latest is None:
        raise HTTPException(status_code=422, detail="Conversation has no customer message")
    return latest

