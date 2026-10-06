import { formatMoney, formatWhen, statusBadgeClass, titleCase } from "../format";
import type { ConversationDetail } from "../types";
import { AssistantPanel } from "./AssistantPanel";

type ContextPanelProps = {
  detail: ConversationDetail | null;
  loading: boolean;
  onSent: (detail: ConversationDetail) => void;
};

export function ContextPanel({ detail, loading, onSent }: ContextPanelProps) {
  if (loading && !detail) {
    return (
      <div className="loading-state" role="status">
        <span className="skeleton" />
        <span className="skeleton short" />
        <p>Loading details…</p>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="empty-state">
        <p className="empty-title">Reply workflow</p>
        <p>Select a conversation to generate a reply from that brand’s knowledge.</p>
      </div>
    );
  }

  const customerMessage = [...detail.messages].reverse().find((message) => message.author_type === "CUSTOMER");

  return (
    <div className="context">
      <AssistantPanel
        brandId={detail.brand.id}
        conversationId={detail.id}
        customerMessage={customerMessage?.body ?? null}
        disabled={loading}
        onSent={onSent}
      />
      <section className="case-card">
        <div className="case-top">
          <div>
            <h2>Case</h2>
            <p className="fact-name">{detail.customer.full_name}</p>
            <p>{detail.customer.email}</p>
          </div>
          <span className={statusBadgeClass(detail.order.status)}>{titleCase(detail.order.status)}</span>
        </div>
        <p className="case-order">
          {detail.order.order_number} · {detail.order.product_name}
        </p>
        <p>{detail.brand.name}</p>
        <dl className="facts">
          <div>
            <dt>Total</dt>
            <dd>{formatMoney(detail.order.total_cents, detail.order.currency)}</dd>
          </div>
          <div>
            <dt>Placed</dt>
            <dd>{formatWhen(detail.order.placed_at)}</dd>
          </div>
          <div>
            <dt>Delivery date</dt>
            <dd>{detail.order.delivered_at ? formatWhen(detail.order.delivered_at) : "Not recorded"}</dd>
          </div>
          <div>
            <dt>Conversation</dt>
            <dd>{titleCase(detail.status)}</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
