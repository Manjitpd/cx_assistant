import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Float, cast, func, literal, select
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, KnowledgeBaseEntry
from app.schemas.retrieval import RetrievedKnowledge

MAX_RESULTS = 5

# Words the English text-search config discards. Dropping them here keeps the
# OR query valid after PostgreSQL removes stop words.
_STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "because",
    "for",
    "from",
    "get",
    "had",
    "has",
    "have",
    "he",
    "her",
    "his",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "like",
    "me",
    "my",
    "no",
    "not",
    "of",
    "on",
    "or",
    "our",
    "please",
    "send",
    "she",
    "so",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "want",
    "was",
    "we",
    "were",
    "will",
    "with",
    "would",
    "you",
    "your",
}


def _or_query(message: str) -> str | None:
    kept: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[0-9A-Za-z]+", message.lower()):
        if len(token) < 2 or token in _STOP_WORDS or token in seen:
            continue
        seen.add(token)
        kept.append(token)
        if len(kept) == 24:
            break
    if not kept:
        return None
    return " or ".join(kept)


async def retrieve_knowledge(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    customer_message: str,
    brand_id: UUID | None = None,
) -> list[RetrievedKnowledge]:
    """Search active knowledge for the brand stored on the conversation.

    ``brand_id`` is ignored when a caller supplies one. The conversation row
    is the only brand source.
    """
    del brand_id
    message = customer_message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Customer message must not be blank")

    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    query_text = _or_query(message)
    if query_text is None:
        return []

    resolved_brand_id = conversation.brand_id
    tsquery = func.websearch_to_tsquery(
        cast(literal("english"), REGCONFIG),
        query_text,
    )
    score = cast(func.ts_rank(KnowledgeBaseEntry.search_vector, tsquery), Float)
    rows = await session.execute(
        select(KnowledgeBaseEntry, score.label("score"))
        .where(
            KnowledgeBaseEntry.brand_id == resolved_brand_id,
            KnowledgeBaseEntry.active.is_(True),
            KnowledgeBaseEntry.search_vector.op("@@")(tsquery),
        )
        .order_by(score.desc(), KnowledgeBaseEntry.title.asc())
        .limit(MAX_RESULTS)
    )
    return [
        RetrievedKnowledge(
            knowledge_entry_id=entry.id,
            title=entry.title,
            category=entry.category,
            content=entry.content,
            score=float(rank),
        )
        for entry, rank in rows.all()
    ]
