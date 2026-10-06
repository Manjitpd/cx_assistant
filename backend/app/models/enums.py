import enum


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class ConversationStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class MessageAuthor(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    AGENT = "AGENT"


class KnowledgeCategory(str, enum.Enum):
    RETURN = "RETURN"
    REFUND = "REFUND"
    SHIPPING = "SHIPPING"
    CANCELLATION = "CANCELLATION"
