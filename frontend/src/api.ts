import type {
  Brand,
  ConversationDetail,
  ConversationMessage,
  ConversationSummary,
  GeneratedReply,
  GenerationLog,
  GenerationState,
  KnowledgeDraft,
  KnowledgeEntry,
} from "./types";


const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const body = (await response.json().catch(() => ({}))) as { detail?: string };

  if (!response.ok) {
    throw new Error(body.detail || "Request failed");
  }

  return body as T;
}

export function fetchBrands(): Promise<Brand[]> {
  return request<Brand[]>("/api/brands");
}

export function fetchKnowledge(brandId: string): Promise<KnowledgeEntry[]> {
  return request<KnowledgeEntry[]>(`/api/brands/${brandId}/knowledge`);
}

export function createKnowledge(brandId: string, draft: KnowledgeDraft): Promise<KnowledgeEntry> {
  return request<KnowledgeEntry>(`/api/brands/${brandId}/knowledge`, {
    method: "POST",
    body: JSON.stringify(draft),
  });
}

export function updateKnowledge(
  brandId: string,
  entryId: string,
  draft: KnowledgeDraft,
): Promise<KnowledgeEntry> {
  const params = new URLSearchParams({ brand_id: brandId });
  return request<KnowledgeEntry>(`/api/knowledge/${entryId}?${params}`, {
    method: "PUT",
    body: JSON.stringify(draft),
  });
}

export function deleteKnowledge(brandId: string, entryId: string): Promise<void> {
  const params = new URLSearchParams({ brand_id: brandId });
  return request<void>(`/api/knowledge/${entryId}?${params}`, { method: "DELETE" });
}

function brandQuery(brandId: string): string {
  return new URLSearchParams({ brand_id: brandId }).toString();
}

export function fetchConversations(brandId: string): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>(`/api/conversations?${brandQuery(brandId)}`);
}

export function fetchConversation(brandId: string, conversationId: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/conversations/${conversationId}?${brandQuery(brandId)}`);
}

export function sendCustomerMessage(
  brandId: string,
  conversationId: string,
  body: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/api/conversations/${conversationId}/messages?${brandQuery(brandId)}`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export function generateReply(conversationId: string): Promise<GeneratedReply> {
  return request<GeneratedReply>(`/api/conversations/${conversationId}/generate-reply`, {
    method: "POST",
  });
}

export function editGeneration(generationId: string, editedReply: string): Promise<GenerationState> {
  return request<GenerationState>(`/api/ai-generations/${generationId}`, {
    method: "PUT",
    body: JSON.stringify({ edited_reply: editedReply }),
  });
}

export function approveGeneration(generationId: string): Promise<GenerationState> {
  return request<GenerationState>(`/api/ai-generations/${generationId}/approve`, {
    method: "POST",
  });
}

export function fetchGenerationLogs(brandId: string, conversationId: string): Promise<GenerationLog[]> {
  return request<GenerationLog[]>(
    `/api/conversations/${conversationId}/generations?${brandQuery(brandId)}`,
  );
}

export function sendGeneration(generationId: string): Promise<ConversationMessage> {
  return request<ConversationMessage>(`/api/ai-generations/${generationId}/send`, {
    method: "POST",
  });
}

export function sendManualReply(
  brandId: string,
  conversationId: string,
  body: string,
  idempotencyKey: string,
): Promise<ConversationDetail> {
  return request<ConversationDetail>(
    `/api/conversations/${conversationId}/manual-reply?${brandQuery(brandId)}`,
    {
      method: "POST",
      body: JSON.stringify({ body }),
      headers: { "Idempotency-Key": idempotencyKey },
    },
  );
}
