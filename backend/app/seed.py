"""Load sample AquaPure and GlowNest data.

Running this again replaces those two brands and their related rows.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AIGenerationLog,
    Brand,
    Conversation,
    ConversationStatus,
    Customer,
    KnowledgeBaseEntry,
    KnowledgeCategory,
    Message,
    MessageAuthor,
    Order,
    OrderStatus,
)


def sid(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"cx-assistant:{name}")


def ago(**delta: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**delta)


POLICIES: dict[str, dict[KnowledgeCategory, tuple[str, str]]] = {
    "aquapure": {
        KnowledgeCategory.RETURN: (
            "Return policy",
            "AquaPure accepts unused items in their original packaging for 30 days "
            "after delivery. Opened filter cartridges cannot be returned. If a pitcher "
            "arrives defective, AquaPure emails a prepaid return label and replaces the "
            "unit. For a change of mind, the customer pays return shipping. AquaPure "
            "does not accept returns from outside the United States.",
        ),
        KnowledgeCategory.REFUND: (
            "Refund policy",
            "After a return reaches the warehouse and passes inspection, AquaPure "
            "refunds the product price to the original payment method within 7 business "
            "days. Outbound shipping is refunded only when the item was defective. "
            "Opened cartridges are not refunded in cash, and AquaPure does not offer "
            "store credit in place of a refused return.",
        ),
        KnowledgeCategory.SHIPPING: (
            "Shipping policy",
            "Standard shipping is free on United States orders of $50 or more. Orders "
            "under $50 cost $6.95. Delivery takes 3 to 5 business days after the order "
            "ships. Orders placed after 2pm Eastern Time ship the next business day. "
            "AquaPure does not ship to Alaska, Hawaii, or any address outside the "
            "United States.",
        ),
        KnowledgeCategory.CANCELLATION: (
            "Cancellation policy",
            "An AquaPure order can be cancelled at no charge before the shipping label "
            "is created. Once a label exists, the order cannot be cancelled, even if "
            "the carrier has not picked it up. The customer waits for delivery and then "
            "uses the return policy. Defective items still qualify for a prepaid "
            "replacement after they arrive.",
        ),
    },
    "glownest": {
        KnowledgeCategory.RETURN: (
            "Return policy",
            "GlowNest accepts returns for 60 days after delivery. Opened skincare can "
            "be returned when more than half of the product remains in the container. "
            "The seal does not need to be intact. GlowNest emails a prepaid return "
            "label for every approved return, including change-of-mind returns. The "
            "policy covers orders shipped to the United States and Canada.",
        ),
        KnowledgeCategory.REFUND: (
            "Refund policy",
            "GlowNest refunds the full product price and the original outbound shipping "
            "charge. There is no restocking fee. The refund is sent to the original "
            "payment method within 5 business days after the carrier scans the prepaid "
            "return label. Customers do not wait for a warehouse inspection before the "
            "refund is issued.",
        ),
        KnowledgeCategory.SHIPPING: (
            "Shipping policy",
            "Orders of $35 or more ship free to the United States and Canada. Orders "
            "under $35 cost $5 for standard shipping. Standard delivery takes 4 to 7 "
            "business days. A $12 two-day option is available in the continental United "
            "States. GlowNest does not ship to PO boxes. Canadian orders use standard "
            "shipping only.",
        ),
        KnowledgeCategory.CANCELLATION: (
            "Cancellation policy",
            "A paid GlowNest order that has not shipped can be cancelled for a full "
            "refund within 12 hours of payment. After 12 hours, an unshipped order can "
            "still be cancelled, but a paid two-day shipping upgrade is not refunded "
            "if the label was already purchased. Shipped orders cannot be cancelled and "
            "follow the return policy. A subscription shipment can be skipped up to 48 "
            "hours before the renewal date.",
        ),
    },
}


def clear_brand(session: Session, slug: str) -> None:
    brand_id = session.scalar(select(Brand.id).where(Brand.slug == slug))
    if brand_id is None:
        return
    session.execute(delete(AIGenerationLog).where(AIGenerationLog.brand_id == brand_id))
    session.execute(delete(Message).where(Message.brand_id == brand_id))
    session.execute(delete(Conversation).where(Conversation.brand_id == brand_id))
    session.execute(delete(Order).where(Order.brand_id == brand_id))
    session.execute(
        delete(KnowledgeBaseEntry).where(KnowledgeBaseEntry.brand_id == brand_id)
    )
    session.execute(delete(Customer).where(Customer.brand_id == brand_id))
    session.execute(delete(Brand).where(Brand.id == brand_id))
    session.flush()


def add_brand(
    session: Session,
    *,
    slug: str,
    name: str,
    customers: list[Customer],
    orders: list[Order],
    conversations: list[Conversation],
    messages: list[Message],
) -> None:
    clear_brand(session, slug)
    brand = Brand(id=sid(f"brand:{slug}"), name=name, slug=slug)
    session.add(brand)
    session.flush()
    for category, (title, content) in POLICIES[slug].items():
        session.add(
            KnowledgeBaseEntry(
                id=sid(f"knowledge:{slug}:{category.value}"),
                brand_id=brand.id,
                category=category,
                title=title,
                content=content,
                active=True,
            )
        )
    session.add_all(customers)
    session.flush()
    session.add_all(orders)
    session.flush()
    session.add_all(conversations)
    session.flush()
    session.add_all(messages)
    session.flush()


def message(
    key: str,
    *,
    brand_id: uuid.UUID,
    conversation_id: uuid.UUID,
    author: MessageAuthor,
    body: str,
    created_at: datetime,
) -> Message:
    return Message(
        id=sid(f"message:{key}"),
        brand_id=brand_id,
        conversation_id=conversation_id,
        author_type=author,
        body=body,
        created_at=created_at,
        updated_at=created_at,
    )


def seed(session: Session) -> None:
    aquapure_id = sid("brand:aquapure")
    glownest_id = sid("brand:glownest")
    maya_id = sid("customer:aquapure:maya")
    luis_id = sid("customer:aquapure:luis")
    priya_id = sid("customer:glownest:priya")
    jonah_id = sid("customer:glownest:jonah")
    pitcher_id = sid("order:aquapure:AP-1042")
    filters_id = sid("order:aquapure:AP-1108")
    serum_id = sid("order:glownest:GN-2201")
    starter_id = sid("order:glownest:GN-2264")
    leak_id = sid("conversation:aquapure:leak")
    cancel_ap_id = sid("conversation:aquapure:cancel")
    serum_thread_id = sid("conversation:glownest:serum")
    cancel_gn_id = sid("conversation:glownest:cancel")

    add_brand(
        session,
        slug="aquapure",
        name="AquaPure",
        customers=[
            Customer(
                id=maya_id,
                brand_id=aquapure_id,
                full_name="Maya Chen",
                email="maya.chen@example.com",
            ),
            Customer(
                id=luis_id,
                brand_id=aquapure_id,
                full_name="Luis Ortega",
                email="luis.ortega@example.com",
            ),
        ],
        orders=[
            Order(
                id=pitcher_id,
                brand_id=aquapure_id,
                customer_id=maya_id,
                order_number="AP-1042",
                product_name="AquaPure Classic Pitcher",
                status=OrderStatus.DELIVERED,
                total_cents=6400,
                currency="USD",
                placed_at=ago(days=12),
            ),
            Order(
                id=filters_id,
                brand_id=aquapure_id,
                customer_id=luis_id,
                order_number="AP-1108",
                product_name="AquaPure Filter 3-Pack",
                status=OrderStatus.SHIPPED,
                total_cents=4200,
                currency="USD",
                placed_at=ago(days=2),
            ),
        ],
        conversations=[
            Conversation(
                id=leak_id,
                brand_id=aquapure_id,
                customer_id=maya_id,
                order_id=pitcher_id,
                subject="Leaking pitcher on order AP-1042",
                status=ConversationStatus.OPEN,
            ),
            Conversation(
                id=cancel_ap_id,
                brand_id=aquapure_id,
                customer_id=luis_id,
                order_id=filters_id,
                subject="Cancel shipped order AP-1108",
                status=ConversationStatus.OPEN,
            ),
        ],
        messages=[
            message(
                "aquapure:leak:1",
                brand_id=aquapure_id,
                conversation_id=leak_id,
                author=MessageAuthor.CUSTOMER,
                body=(
                    "The Classic Pitcher from order AP-1042 arrived last week and leaks "
                    "from the base whenever it is full. Can I return it?"
                ),
                created_at=ago(days=1, hours=5),
            ),
            message(
                "aquapure:leak:2",
                brand_id=aquapure_id,
                conversation_id=leak_id,
                author=MessageAuthor.AGENT,
                body=(
                    "I'm sorry the pitcher is leaking. Defective AquaPure pitchers can "
                    "be returned within 30 days, and we email a prepaid label for "
                    "defects. I can send that label today."
                ),
                created_at=ago(days=1, hours=4),
            ),
            message(
                "aquapure:leak:3",
                brand_id=aquapure_id,
                conversation_id=leak_id,
                author=MessageAuthor.CUSTOMER,
                body="Yes, please send the label. Will this be a refund or a replacement?",
                created_at=ago(days=1, hours=3),
            ),
            message(
                "aquapure:cancel:1",
                brand_id=aquapure_id,
                conversation_id=cancel_ap_id,
                author=MessageAuthor.CUSTOMER,
                body=(
                    "Please cancel order AP-1108. The tracking page says a label was "
                    "created this morning, but I no longer need the filters."
                ),
                created_at=ago(hours=6),
            ),
            message(
                "aquapure:cancel:2",
                brand_id=aquapure_id,
                conversation_id=cancel_ap_id,
                author=MessageAuthor.AGENT,
                body=(
                    "Once an AquaPure shipping label exists, the order cannot be "
                    "cancelled. This shipment is already with the carrier. You can "
                    "refuse delivery or return the unopened 3-pack within 30 days. "
                    "Opened cartridges are not refunded."
                ),
                created_at=ago(hours=5),
            ),
        ],
    )
    add_brand(
        session,
        slug="glownest",
        name="GlowNest",
        customers=[
            Customer(
                id=priya_id,
                brand_id=glownest_id,
                full_name="Priya Shah",
                email="priya.shah@example.com",
            ),
            Customer(
                id=jonah_id,
                brand_id=glownest_id,
                full_name="Jonah Blake",
                email="jonah.blake@example.com",
            ),
        ],
        orders=[
            Order(
                id=serum_id,
                brand_id=glownest_id,
                customer_id=priya_id,
                order_number="GN-2201",
                product_name="GlowNest Night Repair Serum",
                status=OrderStatus.DELIVERED,
                total_cents=4800,
                currency="USD",
                placed_at=ago(days=20),
            ),
            Order(
                id=starter_id,
                brand_id=glownest_id,
                customer_id=jonah_id,
                order_number="GN-2264",
                product_name="GlowNest Shade Starter Set",
                status=OrderStatus.PAID,
                total_cents=3200,
                currency="USD",
                placed_at=ago(hours=3),
            ),
        ],
        conversations=[
            Conversation(
                id=serum_thread_id,
                brand_id=glownest_id,
                customer_id=priya_id,
                order_id=serum_id,
                subject="Return opened Night Repair Serum",
                status=ConversationStatus.OPEN,
            ),
            Conversation(
                id=cancel_gn_id,
                brand_id=glownest_id,
                customer_id=jonah_id,
                order_id=starter_id,
                subject="Cancel unshipped order GN-2264",
                status=ConversationStatus.OPEN,
            ),
        ],
        messages=[
            message(
                "glownest:serum:1",
                brand_id=glownest_id,
                conversation_id=serum_thread_id,
                author=MessageAuthor.CUSTOMER,
                body=(
                    "The Night Repair Serum from order GN-2201 irritated my skin. About "
                    "two-thirds of the bottle is left. I'd like to return it."
                ),
                created_at=ago(days=2, hours=2),
            ),
            message(
                "glownest:serum:2",
                brand_id=glownest_id,
                conversation_id=serum_thread_id,
                author=MessageAuthor.AGENT,
                body=(
                    "You can return opened GlowNest skincare within 60 days when more "
                    "than half the product remains. I'll email a prepaid label. The "
                    "refund includes the product price and the original shipping charge "
                    "after the carrier scans that label."
                ),
                created_at=ago(days=2, hours=1),
            ),
            message(
                "glownest:serum:3",
                brand_id=glownest_id,
                conversation_id=serum_thread_id,
                author=MessageAuthor.CUSTOMER,
                body="Thank you. Please send the label to this email address.",
                created_at=ago(days=2),
            ),
            message(
                "glownest:cancel:1",
                brand_id=glownest_id,
                conversation_id=cancel_gn_id,
                author=MessageAuthor.CUSTOMER,
                body=(
                    "Please cancel order GN-2264. I ordered the wrong shade and it has "
                    "not shipped."
                ),
                created_at=ago(hours=2),
            ),
            message(
                "glownest:cancel:2",
                brand_id=glownest_id,
                conversation_id=cancel_gn_id,
                author=MessageAuthor.AGENT,
                body=(
                    "This order is paid and has not shipped, and it is still inside the "
                    "12-hour cancellation window. I can cancel it now for a full refund "
                    "to the original payment method."
                ),
                created_at=ago(hours=1),
            ),
        ],
    )


def print_summary(session: Session) -> None:
    counts = session.execute(
        select(
            Brand.name,
            func.count(func.distinct(Customer.id)),
            func.count(func.distinct(Order.id)),
            func.count(func.distinct(Conversation.id)),
            func.count(func.distinct(Message.id)),
            func.count(func.distinct(KnowledgeBaseEntry.id)),
        )
        .outerjoin(Customer, Customer.brand_id == Brand.id)
        .outerjoin(Order, Order.brand_id == Brand.id)
        .outerjoin(Conversation, Conversation.brand_id == Brand.id)
        .outerjoin(Message, Message.brand_id == Brand.id)
        .outerjoin(KnowledgeBaseEntry, KnowledgeBaseEntry.brand_id == Brand.id)
        .group_by(Brand.name)
        .order_by(Brand.name)
    ).all()
    for name, customers, orders, conversations, messages, policies in counts:
        print(
            f"{name}: {customers} customers, {orders} orders, "
            f"{conversations} conversations, {messages} messages, {policies} policies"
        )


def main() -> None:
    engine = create_engine(get_settings().database_url)
    with Session(engine) as session:
        seed(session)
        session.commit()
        print_summary(session)
    engine.dispose()


if __name__ == "__main__":
    main()
