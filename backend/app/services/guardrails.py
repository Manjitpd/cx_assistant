"""Server-side checks for AI drafts.

The model can suggest a reply, but policy claims, order facts, exceptions,
and completed actions are accepted only when retrieved knowledge or the
order record supports them.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.models.enums import KnowledgeCategory, OrderStatus
from app.schemas.conversation import OrderSummary
from app.schemas.generation import EvidenceStatus, GeneratedReply
from app.schemas.retrieval import RetrievedKnowledge

_WINDOW = re.compile(r"(?:within|for)\s+(\d+)\s+days\s+(?:of|after)\s+delivery", re.IGNORECASE)
_STATED_DAYS = re.compile(r"\b(\d+)\s+days?\s+ago\b", re.IGNORECASE)
_NEW_REFUND = re.compile(
    r"\b(?:can i|could i|may i)\s+(?:get|have|request)\s+a\s+refund\b|"
    r"\b(?:get a refund|want a refund|refund me)\b",
    re.IGNORECASE,
)
_SHIPPING = re.compile(r"\b(shipping|ship)\b", re.IGNORECASE)
_ALREADY = re.compile(
    r"\b(already|been issued|been processed|has my refund|was i refunded|did you refund)\b",
    re.IGNORECASE,
)
_DEFECT = re.compile(r"\b(broken|defective|damaged)\b", re.IGNORECASE)
_BRANDISH = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-zA-Z]+)+\b")
_PROMISE = re.compile(
    r"\b(you can get a refund|you will (?:get|receive) a refund|refund is approved|"
    r"approve (?:your|the|a) refund|eligible for a refund|we can refund|full refund)\b",
    re.IGNORECASE,
)
_REFUND_DONE = re.compile(
    r"\b(refund has been (?:issued|processed|completed)|refund was (?:issued|processed)|"
    r"already been refunded|already refunded|processed your refund|"
    r"refund has already been|i(?:'ve| have) already processed)\b",
    re.IGNORECASE,
)
_CANCEL_DONE = re.compile(
    r"\b(already been cancelled|has been cancelled|order was cancelled|i'?ve cancelled)\b",
    re.IGNORECASE,
)
_SHIP_DONE = re.compile(r"\b(has been shipped|already shipped|we have shipped)\b", re.IGNORECASE)
_DELIVER_DONE = re.compile(r"\b(has been delivered|already delivered)\b", re.IGNORECASE)
_LABEL_DONE = re.compile(
    r"\b(label has been sent|label was sent|sent a prepaid label|prepaid label is on)\b",
    re.IGNORECASE,
)
_EXCEPTION = re.compile(r"\bexception\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(not|no|cannot|can't|don't|doesn't|without)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Assessment:
    status: EvidenceStatus
    warning: str | None
    safe_reply: str
    used_ids: list[UUID]
    skip_model: bool = False
    refund_decision: str = "not_applicable"


def assess(
    *,
    customer_message: str,
    knowledge: Sequence[RetrievedKnowledge],
    order: OrderSummary,
    brand_name: str,
) -> Assessment:
    message = customer_message.strip()
    refund_entries = [entry for entry in knowledge if entry.category == KnowledgeCategory.REFUND]
    shipping_entries = [entry for entry in knowledge if entry.category == KnowledgeCategory.SHIPPING]
    if _NEW_REFUND.search(message) and not refund_entries:
        return _unknown_policy(brand_name, "refund")
    if _SHIPPING.search(message) and not shipping_entries and not _NEW_REFUND.search(message):
        return _unknown_policy(brand_name, "shipping")
    if _ALREADY.search(message) and not _NEW_REFUND.search(message):
        return _unknown_action(order)

    if not _NEW_REFUND.search(message):
        return Assessment(
            status=EvidenceStatus.SUPPORTED,
            warning=None,
            safe_reply=_fallback(brand_name),
            used_ids=[entry.knowledge_entry_id for entry in knowledge[:1]],
        )

    windows = _windows(refund_entries)
    unique = sorted({days for days, _entry in windows})
    if len(unique) > 1:
        return _conflict(refund_entries, unique)
    if _DEFECT.search(message) and not _policy_covers_defect(knowledge) and _decision(unique, message, order) != "approved":
        return _broken(brand_name, order, unique, refund_entries)
    if not unique:
        return Assessment(
            status=EvidenceStatus.INSUFFICIENT_INFORMATION,
            warning="The retrieved refund policy does not state a delivery window.",
            safe_reply=(
                f"The retrieved {brand_name} refund policy does not state a delivery window "
                f"I can apply to order {order.order_number}, so I can't confirm a refund."
            ),
            used_ids=[entry.knowledge_entry_id for entry in refund_entries],
            refund_decision="unconfirmed",
        )
    return _window_decision(brand_name, order, message, unique[0], refund_entries)


def guard_reply(
    draft: GeneratedReply,
    *,
    customer_message: str,
    knowledge: Sequence[RetrievedKnowledge],
    order: OrderSummary,
    brand_name: str,
) -> GeneratedReply:
    if draft.warning and "not retrieved for this brand" in draft.warning:
        return draft
    assessment = assess(
        customer_message=customer_message,
        knowledge=knowledge,
        order=order,
        brand_name=brand_name,
    )
    if assessment.skip_model:
        return _from_assessment(assessment)

    violations = _violations(
        draft.suggested_reply,
        knowledge=knowledge,
        order=order,
        brand_name=brand_name,
        refund_decision=assessment.refund_decision,
    )
    replace = bool(violations) or assessment.refund_decision == "conflict"
    if not replace:
        return GeneratedReply(
            suggested_reply=draft.suggested_reply.strip(),
            evidence_status=_stricter(draft.evidence_status, assessment.status),
            warning=_join(assessment.warning, draft.warning),
            used_knowledge_ids=draft.used_knowledge_ids,
        )

    status = assessment.status
    reply = assessment.safe_reply
    if any("not in this brand's retrieved knowledge" in item for item in violations):
        status = EvidenceStatus.HUMAN_REVIEW_REQUIRED
        reply = (
            f"I can only use {brand_name} policies that were retrieved for this conversation. "
            "The draft included policy text that was not retrieved, so I can't confirm a refund, "
            "return window, shipping rule, or compensation. A teammate will review it."
        )
    return GeneratedReply(
        suggested_reply=reply,
        evidence_status=status,
        warning=_join(assessment.warning, *violations),
        used_knowledge_ids=assessment.used_ids,
    )


def assessment_reply(assessment: Assessment) -> GeneratedReply:
    return _from_assessment(assessment)


def _from_assessment(assessment: Assessment) -> GeneratedReply:
    return GeneratedReply(
        suggested_reply=assessment.safe_reply,
        evidence_status=assessment.status,
        warning=assessment.warning,
        used_knowledge_ids=assessment.used_ids,
    )


def _article(name: str) -> str:
    return "an" if name[:1].lower() in "aeiou" else "a"


def _unknown_policy(brand_name: str, topic: str) -> Assessment:
    article = _article(brand_name)
    if topic == "shipping":
        reply = (
            f"I don't have {article} {brand_name} shipping policy for this request, so I can't confirm "
            "a shipping cost or a delivery time. A teammate will review it."
        )
        warning = "No relevant shipping policy was retrieved. Human review is required."
    else:
        reply = (
            f"I don't have {article} {brand_name} refund policy for this request, so I can't confirm "
            "a refund, a return window, or compensation. A teammate will review it."
        )
        warning = "No relevant refund policy was retrieved. Human review is required."
    return Assessment(
        status=EvidenceStatus.HUMAN_REVIEW_REQUIRED,
        warning=warning,
        safe_reply=reply,
        used_ids=[],
        skip_model=True,
        refund_decision="no_policy",
    )


def _unknown_action(order: OrderSummary) -> Assessment:
    return Assessment(
        status=EvidenceStatus.INSUFFICIENT_INFORMATION,
        warning="The order record does not confirm the action the customer asked about.",
        safe_reply=(
            f"Order {order.order_number} has status {order.status.value} in the order record. "
            "That record does not show that a refund, replacement label, or cancellation "
            "has already been completed."
        ),
        used_ids=[],
        skip_model=True,
    )


def _conflict(entries: Sequence[RetrievedKnowledge], windows: list[int]) -> Assessment:
    listed = " and ".join(f"{days} days" for days in windows)
    excerpts = " ".join(f"{entry.title}: {_excerpt(entry.content)}" for entry in entries)
    return Assessment(
        status=EvidenceStatus.HUMAN_REVIEW_REQUIRED,
        warning=f"Retrieved refund policies conflict ({listed}). {excerpts}",
        safe_reply=(
            f"The retrieved refund policies disagree about the allowed window ({listed}). "
            "I can't choose between them, so a teammate needs to review this before a refund is promised."
        ),
        used_ids=[entry.knowledge_entry_id for entry in entries],
        refund_decision="conflict",
    )


def _broken(
    brand_name: str,
    order: OrderSummary,
    windows: list[int],
    entries: Sequence[RetrievedKnowledge],
) -> Assessment:
    window = ""
    if len(windows) == 1:
        window = (
            f" The {brand_name} refund policy permits a refund within {windows[0]} days of delivery,"
            " and that text does not add an exception for a broken product."
        )
    return Assessment(
        status=EvidenceStatus.HUMAN_REVIEW_REQUIRED,
        warning="The retrieved policies do not describe an exception for a broken product.",
        safe_reply=(
            f"The retrieved policies do not describe an exception for a broken product.{window} "
            f"I can't approve a refund for order {order.order_number} from an exception that "
            "is not written in the retrieved policies."
        ),
        used_ids=[entry.knowledge_entry_id for entry in entries],
        refund_decision="denied",
    )


def _window_decision(
    brand_name: str,
    order: OrderSummary,
    message: str,
    days: int,
    entries: Sequence[RetrievedKnowledge],
) -> Assessment:
    decision = _decision([days], message, order)
    used = [entry.knowledge_entry_id for entry in entries]
    policy = f"The {brand_name} refund policy permits a refund within {days} days of delivery."
    if decision == "approved" and order.delivered_at is not None:
        return Assessment(
            status=EvidenceStatus.SUPPORTED,
            warning=None,
            safe_reply=(
                f"{policy} Order {order.order_number} was delivered on {_calendar(order.delivered_at)}, "
                "which is inside that window. The order record does not show that the refund "
                "has already been issued."
            ),
            used_ids=used,
            refund_decision="approved",
        )
    if decision == "denied" and order.delivered_at is not None:
        return Assessment(
            status=EvidenceStatus.SUPPORTED,
            warning="The refund request is outside the allowed window.",
            safe_reply=(
                f"{policy} Order {order.order_number} was delivered on {_calendar(order.delivered_at)}, "
                "which is outside that window, so I can't approve a refund."
            ),
            used_ids=used,
            refund_decision="denied",
        )
    stated = _stated_days(message)
    if decision == "denied" and stated is not None:
        return Assessment(
            status=EvidenceStatus.PARTIALLY_SUPPORTED,
            warning=(
                f"The customer says the order was received {stated} days ago, which is outside "
                f"the {days}-day refund policy. The delivery date is not recorded on the order."
            ),
            safe_reply=(
                f"{policy} Order {order.order_number} does not have a delivery date recorded, "
                f"so I can't confirm a refund. The customer says it was received {stated} days ago, "
                "which would fall outside that policy, but the order record does not confirm that timing."
            ),
            used_ids=used,
            refund_decision="denied",
        )
    if decision == "conflict":
        return Assessment(
            status=EvidenceStatus.HUMAN_REVIEW_REQUIRED,
            warning=(
                "The customer timing and the recorded delivery date disagree about whether "
                "the refund window is still open."
            ),
            safe_reply=(
                f"{policy} The customer timing and the delivery date recorded for order "
                f"{order.order_number} disagree, so I can't approve a refund until a teammate checks both."
            ),
            used_ids=used,
            refund_decision="conflict",
        )
    return Assessment(
        status=EvidenceStatus.INSUFFICIENT_INFORMATION,
        warning="The delivery date is not recorded, so the refund window cannot be confirmed.",
        safe_reply=(
            f"{policy} Order {order.order_number} does not have a delivery date recorded, "
            "so I can't confirm whether a refund is available."
        ),
        used_ids=used,
        refund_decision="unconfirmed",
    )


def _decision(windows: list[int], message: str, order: OrderSummary) -> str:
    if len(windows) != 1:
        return "unconfirmed" if not windows else "conflict"
    limit = windows[0]
    recorded = _age_days(order.delivered_at)
    stated = _stated_days(message)
    recorded_inside = None if recorded is None else recorded <= limit
    stated_inside = None if stated is None else stated <= limit
    if recorded_inside is not None and stated_inside is not None and recorded_inside != stated_inside:
        return "conflict"
    if recorded_inside is True:
        return "approved"
    if recorded_inside is False or stated_inside is False:
        return "denied"
    return "unconfirmed"


def _violations(
    reply: str,
    *,
    knowledge: Sequence[RetrievedKnowledge],
    order: OrderSummary,
    brand_name: str,
    refund_decision: str,
) -> list[str]:
    found: list[str] = []
    policy = "\n".join(entry.content for entry in knowledge)
    for name in _BRANDISH.findall(reply):
        if name.lower() in brand_name.lower() or name.lower() in policy.lower():
            continue
        found.append(f"The reply mentions {name}, which is not in this brand's retrieved knowledge.")
    for number in re.findall(r"\b(\d+)\s*-?\s*days?\b", reply, flags=re.IGNORECASE):
        if re.search(rf"\b{number}\b", policy) is None:
            found.append(f"The reply states a {number}-day policy that was not retrieved.")
    for amount in re.findall(r"\$\d+(?:\.\d{2})?", reply):
        if amount not in policy and amount not in _money(order):
            found.append(f"The reply states {amount}, which is not in the retrieved policies or the order.")
    if _claimed(_PROMISE, reply) and refund_decision != "approved":
        found.append("The reply promises a refund the policy and order do not support.")
    if _claimed(_REFUND_DONE, reply):
        found.append("The reply says a refund already happened, and the order record does not show that.")
    if _claimed(_LABEL_DONE, reply):
        found.append("The reply says a label was sent, and the order record does not show that.")
    if _claimed(_CANCEL_DONE, reply) and order.status != OrderStatus.CANCELLED:
        found.append("The reply says the order was cancelled, and the order record does not show that.")
    if _claimed(_SHIP_DONE, reply) and order.status not in {OrderStatus.SHIPPED, OrderStatus.DELIVERED}:
        found.append("The reply says the order has shipped, and the order record does not show that.")
    if _claimed(_DELIVER_DONE, reply) and order.status != OrderStatus.DELIVERED:
        found.append("The reply says the order was delivered, and the order record does not show that.")
    exception = _EXCEPTION.search(reply)
    if exception and not _policy_covers_defect(knowledge) and not _negated(reply, exception.start()):
        found.append("The reply invents an exception that is not in the retrieved policies.")
    return found


def _windows(entries: Sequence[RetrievedKnowledge]) -> list[tuple[int, RetrievedKnowledge]]:
    found: list[tuple[int, RetrievedKnowledge]] = []
    for entry in entries:
        for match in _WINDOW.finditer(entry.content):
            found.append((int(match.group(1)), entry))
    return found


def _policy_covers_defect(knowledge: Sequence[RetrievedKnowledge]) -> bool:
    text = "\n".join(entry.content for entry in knowledge)
    return _DEFECT.search(text) is not None


def _stated_days(message: str) -> int | None:
    match = _STATED_DAYS.search(message)
    if match is None:
        return None
    return int(match.group(1))


def _age_days(moment: datetime | None) -> int | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    current = datetime.now(timezone.utc)
    return (current.date() - moment.astimezone(timezone.utc).date()).days


def _calendar(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).date().isoformat()


def _money(order: OrderSummary) -> str:
    return f"{order.currency} {order.total_cents / 100:.2f}"


def _claimed(pattern: re.Pattern[str], text: str) -> bool:
    return any(not _negated(text, match.start()) for match in pattern.finditer(text))


def _negated(text: str, start: int) -> bool:
    return _NEGATION.search(text[max(0, start - 60) : start]) is not None


def _excerpt(content: str) -> str:
    cleaned = " ".join(content.split())
    if len(cleaned) <= 140:
        return cleaned
    return cleaned[:139].rstrip() + "…"


def _fallback(brand_name: str) -> str:
    return (
        f"Thank you for writing to {brand_name}. I can't confirm a policy outcome from "
        "the retrieved knowledge, so a teammate will review the conversation."
    )


def _stricter(left: EvidenceStatus, right: EvidenceStatus) -> EvidenceStatus:
    rank = {
        EvidenceStatus.HUMAN_REVIEW_REQUIRED: 0,
        EvidenceStatus.INSUFFICIENT_INFORMATION: 1,
        EvidenceStatus.PARTIALLY_SUPPORTED: 2,
        EvidenceStatus.SUPPORTED: 3,
    }
    return left if rank[left] <= rank[right] else right


def _join(*parts: str | None) -> str | None:
    seen: list[str] = []
    for part in parts:
        if not part:
            continue
        text = part.strip()
        if text and text not in seen:
            seen.append(text)
    if not seen:
        return None
    return " ".join(seen)
