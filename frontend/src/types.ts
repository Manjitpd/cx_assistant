export type Category = "RETURN" | "REFUND" | "SHIPPING" | "CANCELLATION";

export type Brand = {
  id: string;
  name: string;
  slug: string;
};

export type KnowledgeEntry = {
  id: string;
  brand_id: string;
  title: string;
  category: Category;
  content: string;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type KnowledgeDraft = {
  title: string;
  category: Category;
  content: string;
  active: boolean;
};

export type MessageAuthor = "CUSTOMER" | "AGENT";

export type CustomerSummary = {
  id: string;
  full_name: string;
  email: string;
};

export type OrderSummary = {
  id: string;
  order_number: string;
  product_name: string;
  status: string;
  total_cents: number;
  currency: string;
  placed_at: string;
  delivered_at: string | null;
};

export type ConversationSummary = {
  id: string;
  subject: string;
  status: string;
  updated_at: string;
  brand: Brand;
  customer: CustomerSummary;
  order: OrderSummary;
};

export type ConversationMessage = {
  id: string;
  author_type: MessageAuthor;
  body: string;
  created_at: string;
};

export type ConversationDetail = ConversationSummary & {
  created_at: string;
  messages: ConversationMessage[];
};

export type EvidenceStatus =
  | "SUPPORTED"
  | "PARTIALLY_SUPPORTED"
  | "INSUFFICIENT_INFORMATION"
  | "HUMAN_REVIEW_REQUIRED";

export type RetrievedKnowledge = {
  knowledge_entry_id: string;
  title: string;
  category: Category;
  content: string;
  score: number;
};

export type GenerationStatus = "AI_GENERATED" | "EDITED" | "APPROVED" | "SENT";

export type GeneratedReply = {
  suggested_reply: string;
  retrieved_knowledge: RetrievedKnowledge[];
  evidence_status: EvidenceStatus;
  warning: string | null;
  generation_id: string;
  status: GenerationStatus;
};

export type RetrievedContextItem = {
  knowledge_entry_id: string;
  title: string;
  category: string;
  content: string;
  score: number;
};

export type GenerationLog = {
  id: string;
  conversation_id: string;
  customer_message_id: string;
  brand_id: string;
  retrieved_knowledge_ids: string[];
  retrieved_context: RetrievedContextItem[];
  model_name: string | null;
  suggested_reply: string;
  edited_reply: string | null;
  final_reply: string | null;
  evidence_status: EvidenceStatus;
  warning: string | null;
  error_detail: string | null;
  created_at: string;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  status: GenerationStatus;
};

export type GenerationState = {
  id: string;
  status: GenerationStatus;
  suggested_reply: string;
  edited_reply: string | null;
  final_reply: string | null;
  evidence_status: EvidenceStatus;
  warning: string | null;
};

export const CATEGORIES: Category[] = ["RETURN", "REFUND", "SHIPPING", "CANCELLATION"];

export const CATEGORY_LABEL: Record<Category, string> = {
  RETURN: "Return",
  REFUND: "Refund",
  SHIPPING: "Shipping",
  CANCELLATION: "Cancellation",
};
