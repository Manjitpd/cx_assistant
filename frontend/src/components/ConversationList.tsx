import { formatWhen, initials, statusBadgeClass, titleCase } from "../format";
import type { ConversationSummary } from "../types";

type ConversationListProps = {
  conversations: ConversationSummary[];
  selectedId: string;
  loading: boolean;
  onSelect: (conversationId: string) => void;
};

export function ConversationList({ conversations, selectedId, loading, onSelect }: ConversationListProps) {
  return (
    <div className="thread-list">
      <h2>Inbox</h2>
      {loading ? (
        <div className="loading-state" role="status">
          <span className="skeleton" />
          <span className="skeleton short" />
          <p>Loading conversations…</p>
        </div>
      ) : null}
      {!loading && conversations.length === 0 ? (
        <div className="empty-state">
          <p className="empty-title">No conversations</p>
          <p>This brand has no conversations yet.</p>
        </div>
      ) : null}
      <ul>
        {conversations.map((conversation) => (
          <li key={conversation.id}>
            <button
              type="button"
              className={conversation.id === selectedId ? "thread selected" : "thread"}
              aria-current={conversation.id === selectedId ? "true" : undefined}
              onClick={() => onSelect(conversation.id)}
            >
              <span className="avatar" aria-hidden="true">
                {initials(conversation.customer.full_name)}
              </span>
              <span className="thread-copy">
                <strong>{conversation.customer.full_name}</strong>
                <span>{conversation.subject}</span>
                <span className={statusBadgeClass(conversation.status)}>{titleCase(conversation.status)}</span>
                <small>
                  {conversation.order.order_number} · {titleCase(conversation.order.status)} · {formatWhen(conversation.updated_at)}
                </small>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
