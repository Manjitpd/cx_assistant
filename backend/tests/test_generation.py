"""AI reply generation. The OpenRouter key stays on the server."""

import asyncio
import json
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

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
from app.services.ai_provider import (
    HTTP_WARNING,
    TIMEOUT_WARNING,
    UNCONFIGURED_WARNING,
    OpenRouterProvider,
    ProviderError,
)
from app.services.generation import generate_reply

AQUA_POLICY = UUID("11111111-1111-4111-8111-111111111111")
GLOW_POLICY = UUID("22222222-2222-4222-8222-222222222222")
OTHER_POLICY = "GlowNest accepts returns for 60 days and refunds shipping."


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def conversation() -> ConversationDetail:
    created = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
    return ConversationDetail(
        id=uuid4(),
        subject="Leaking pitcher on order AP-1042",
        status=ConversationStatus.OPEN,
        updated_at=created,
        created_at=created,
        brand=BrandSummary(id=uuid4(), name="AquaPure", slug="aquapure"),
        customer=CustomerSummary(id=uuid4(), full_name="Maya Chen", email="maya.chen@example.com"),
        order=OrderSummary(
            id=uuid4(),
            order_number="AP-1042",
            product_name="AquaPure Classic Pitcher",
            status=OrderStatus.DELIVERED,
            total_cents=6400,
            currency="USD",
            placed_at=created,
        ),
        messages=[
            MessageRead(
                id=uuid4(),
                author_type=MessageAuthor.CUSTOMER,
                body="The Classic Pitcher leaks from the base.",
                created_at=created,
            )
        ],
    )


def policy() -> RetrievedKnowledge:
    return RetrievedKnowledge(
        knowledge_entry_id=AQUA_POLICY,
        title="Return policy",
        category="RETURN",
        content="AquaPure accepts unused items for 30 days after delivery.",
        score=0.2,
    )


class Capture:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.messages = None
        self.schema = None
        self.calls = 0

    async def generate_json(self, *, messages, json_schema):
        self.calls += 1
        self.messages = messages
        self.schema = json_schema
        return self.payload


def combined(messages: list[dict[str, str]]) -> str:
    return "\n".join(item["content"] for item in messages)


async def main() -> None:
    detail = conversation()
    silent = Capture({})
    empty = await generate_reply(detail, "Can I return this pitcher?", [], provider=silent)
    expect(silent.calls == 0, "empty knowledge called the provider")
    expect(empty.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, empty.evidence_status)
    expect(empty.used_knowledge_ids == [], empty.used_knowledge_ids)
    expect("30 days" not in empty.suggested_reply, empty.suggested_reply)
    expect("Human review is required" in (empty.warning or ""), empty.warning)
    expect("AquaPure" in empty.suggested_reply, empty.suggested_reply)

    supported = Capture(
        {
            "suggested_reply": "AquaPure can take an unused pitcher back within 30 days.",
            "evidence_status": "supported",
            "warning": None,
            "used_knowledge_ids": [str(AQUA_POLICY)],
        }
    )
    draft = await generate_reply(
        detail,
        "Can I return this defective pitcher?",
        [policy()],
        provider=supported,
    )
    expect(draft.evidence_status == EvidenceStatus.SUPPORTED, draft)
    expect(draft.used_knowledge_ids == [AQUA_POLICY], draft.used_knowledge_ids)
    expect(draft.warning is None, draft.warning)
    text = combined(supported.messages)
    for phrase in (
        "Brand identity",
        "AquaPure",
        "Conversation history",
        "The Classic Pitcher leaks from the base.",
        "Order information",
        "AP-1042",
        "delivery_date: not recorded",
        "Retrieved brand-specific policies",
        "AquaPure accepts unused items for 30 days after delivery.",
        "Latest customer message",
        "Can I return this defective pitcher?",
        "Do not invent refund policies.",
        "Do not invent return windows.",
        "Do not promise compensation without evidence.",
        "Do not invent order information.",
        "Do not use knowledge from another brand.",
        "Do not pretend information exists when it does not.",
        "source of truth",
    ):
        expect(phrase in text, f"prompt missing {phrase}")
    expect(OTHER_POLICY not in text, "prompt included another brand")
    expect(supported.schema["required"] == [
        "suggested_reply",
        "evidence_status",
        "warning",
        "used_knowledge_ids",
    ], supported.schema)

    foreign = Capture(
        {
            "suggested_reply": OTHER_POLICY,
            "evidence_status": "supported",
            "warning": None,
            "used_knowledge_ids": [str(GLOW_POLICY)],
        }
    )
    blocked = await generate_reply(detail, "What is the return window?", [policy()], provider=foreign)
    expect(blocked.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, blocked)
    expect(blocked.used_knowledge_ids == [], blocked.used_knowledge_ids)
    expect(OTHER_POLICY not in blocked.suggested_reply, blocked.suggested_reply)
    expect("60 days" not in blocked.suggested_reply, blocked.suggested_reply)

    clarifying = Capture(
        {
            "suggested_reply": "I can't confirm that from the policies I have. A teammate will review it.",
            "evidence_status": "needs_review",
            "warning": "The return policy does not mention this case.",
            "used_knowledge_ids": [],
        }
    )
    review = await generate_reply(detail, "Can I get store credit?", [policy()], provider=clarifying)
    expect(review.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, review)
    expect(review.used_knowledge_ids == [], review.used_knowledge_ids)
    expect("store credit" not in review.suggested_reply.lower() or "can't confirm" in review.suggested_reply, review)

    class Boom:
        async def generate_json(self, **kwargs):
            raise ProviderError(TIMEOUT_WARNING)

    timed_out = await generate_reply(detail, "Can I return this?", [policy()], provider=Boom())
    expect(timed_out.evidence_status == EvidenceStatus.HUMAN_REVIEW_REQUIRED, timed_out)
    expect(timed_out.warning == TIMEOUT_WARNING, timed_out.warning)
    expect("30 days" not in timed_out.suggested_reply, timed_out.suggested_reply)

    try:
        await generate_reply(detail, "   ", [policy()], provider=silent)
        raise SystemExit("blank message was accepted")
    except Exception as error:
        expect(getattr(error, "status_code", None) == 422, error)

    seen = {}

    def transport(url, payload, headers, timeout):
        seen["url"] = url
        seen["payload"] = payload
        seen["headers"] = headers
        seen["timeout"] = timeout
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "suggested_reply": "Quoted from policy.",
                                "evidence_status": "supported",
                                "warning": None,
                                "used_knowledge_ids": [str(AQUA_POLICY)],
                            }
                        )
                    }
                }
            ]
        }

    provider = OpenRouterProvider(
        api_key="test-openrouter-key",
        model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=12,
        app_name="Datastraw CX Assistant",
        transport=transport,
    )
    parsed = await provider.generate_json(messages=[{"role": "system", "content": "rules"}], json_schema={"type": "object"})
    expect(parsed["suggested_reply"] == "Quoted from policy.", parsed)
    expect(seen["url"] == "https://openrouter.ai/api/v1/chat/completions", seen["url"])
    expect(seen["timeout"] == 12, seen["timeout"])
    expect(seen["headers"]["Authorization"] == "Bearer test-openrouter-key", "authorization missing")
    expect("test-openrouter-key" not in json.dumps(seen["payload"]), "key leaked into the request body")
    expect(seen["payload"]["model"] == "openai/gpt-4o-mini", seen["payload"]["model"])
    expect(seen["payload"]["response_format"]["type"] == "json_schema", seen["payload"]["response_format"])
    expect("test-openrouter-key" not in repr(provider), repr(provider))

    def explode(*args):
        raise AssertionError("provider called the network")

    unconfigured = OpenRouterProvider(
        api_key="",
        model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=5,
        app_name="Datastraw CX Assistant",
        transport=explode,
    )
    try:
        await unconfigured.generate_json(messages=[], json_schema={})
        raise SystemExit("missing key was accepted")
    except ProviderError as error:
        expect(error.warning == UNCONFIGURED_WARNING, error.warning)

    def time_out(*args):
        raise TimeoutError("timed out")

    slow = OpenRouterProvider(
        api_key="test-openrouter-key",
        model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=5,
        app_name="Datastraw CX Assistant",
        transport=time_out,
    )
    try:
        await slow.generate_json(messages=[], json_schema={})
        raise SystemExit("timeout was ignored")
    except ProviderError as error:
        expect(error.warning == TIMEOUT_WARNING, error.warning)

    def http_error(*args):
        raise urllib.error.HTTPError(
            "https://openrouter.ai/api/v1/chat/completions",
            401,
            "Unauthorized",
            hdrs=None,
            fp=None,
        )

    rejected = OpenRouterProvider(
        api_key="test-openrouter-key",
        model="openai/gpt-4o-mini",
        base_url="https://openrouter.ai/api/v1",
        timeout_seconds=5,
        app_name="Datastraw CX Assistant",
        transport=http_error,
    )
    try:
        await rejected.generate_json(messages=[], json_schema={})
        raise SystemExit("HTTP error was ignored")
    except ProviderError as error:
        expect(error.warning == HTTP_WARNING, error.warning)
        expect("test-openrouter-key" not in error.warning, error.warning)

    root = Path(__file__).resolve().parents[2] / "frontend"
    for path in root.rglob("*"):
        if "node_modules" in path.parts or not path.is_file():
            continue
        if path.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx", ".html", ".env"}:
            continue
        source = path.read_text(encoding="utf-8")
        expect("OPENROUTER" not in source and "openrouter.ai" not in source, f"frontend secret surface: {path.name}")

    print("generation checks passed")


if __name__ == "__main__":
    asyncio.run(main())
