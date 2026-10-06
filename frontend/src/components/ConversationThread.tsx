import { useEffect, useRef } from "react";
import { formatWhen, statusBadgeClass, titleCase } from "../format";
import type { ConversationDetail, MessageAuthor } from "../types";

type ConversationThreadProps = {
  detail: ConversationDetail | null;
  loading: boolean;
  sending: boolean;
  notice: string;
  mode: MessageAuthor;
  draft: string;
  onMode: (mode: MessageAuthor) => void;
  onDraft: (value: string) => void;
  onSend: () => void;
};

export function ConversationThread({
  detail,
  loading,
  sending,
  notice,
  mode,
  draft,
  onMode,
  onDraft,
  onSend,
}: ConversationThreadProps) {
  const historyEnd = useRef<HTMLDivElement>(null);
  const latestCustomer = detail
    ? [...detail.messages].reverse().find((message) => message.author_type === "CUSTOMER")
    : undefined;
  const busy = sending || loading;

  useEffect(() => {
    historyEnd.current?.scrollIntoView({ block: "end" });
  }, [detail?.id, detail?.messages.length]);

  if (!detail && loading) {
    return (
      <div className="loading-state" role="status">
        <span className="skeleton" />
        <span className="skeleton" />
        <span className="skeleton short" />
        <p>Loading conversation…</p>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="empty-state">
        <p className="empty-title">Select a conversation</p>
        <p>Choose a thread from the inbox. The customer message, reply draft, and history stay on this page.</p>
      </div>
    );
  }

  return (
    <div className="thread-view" aria-busy={loading}>
      <header className="detail-head">
        <div className="detail-title-row">
          <h2>{detail.subject}</h2>
          <span className={statusBadgeClass(detail.status)}>{titleCase(detail.status)}</span>
        </div>
        <p>
          {detail.brand.name} · {detail.customer.full_name}
        </p>
      </header>

      {notice ? (
        <p className="notice" role="status">
          {notice}
        </p>
      ) : null}

      {latestCustomer ? (
        <section className="latest-customer" aria-label="Customer message">
          <h3 className="section-label">Customer message</h3>
          <div className="bubble-meta">
            <span>{detail.customer.full_name}</span>
            <time dateTime={latestCustomer.created_at}>{formatWhen(latestCustomer.created_at)}</time>
          </div>
          <p>{latestCustomer.body}</p>
        </section>
      ) : (
        <div className="empty-state">
          <p className="empty-title">No customer message</p>
          <p>This conversation has no customer message yet.</p>
        </div>
      )}

      <div className="history-wrap">
        <h3 className="section-label">Conversation history</h3>
        <div className="history" aria-label="Conversation history">
          {loading ? (
            <div className="loading-state" role="status">
              <span className="skeleton" />
              <span className="skeleton short" />
              <p>Loading messages…</p>
            </div>
          ) : null}
          {!loading && detail.messages.length === 0 ? (
            <div className="empty-state">
              <p className="empty-title">No messages yet</p>
              <p>Messages you send appear here and stay after a refresh.</p>
            </div>
          ) : null}
          {detail.messages.map((message) => {
            const fromCustomer = message.author_type === "CUSTOMER";
            return (
              <article key={message.id} className={fromCustomer ? "bubble customer" : "bubble agent"}>
                <div className="bubble-meta">
                  <span>{fromCustomer ? detail.customer.full_name : "Agent"}</span>
                  <time dateTime={message.created_at}>{formatWhen(message.created_at)}</time>
                </div>
                <p>{message.body}</p>
              </article>
            );
          })}
          <div ref={historyEnd} />
        </div>
      </div>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          onSend();
        }}
      >
        <div className="mode-switch" role="group" aria-label="Sender">
          <button type="button" className={mode === "CUSTOMER" ? "selected" : ""} disabled={busy} onClick={() => onMode("CUSTOMER")}>
            Customer
          </button>
          <button type="button" className={mode === "AGENT" ? "selected" : ""} disabled={busy} onClick={() => onMode("AGENT")}>
            Agent
          </button>
        </div>
        <label>
          <span className="composer-label">
            {mode === "CUSTOMER" ? "Message from the customer" : "Manual reply from the agent"}
          </span>
          {mode === "AGENT" ? <span className="hint">Sends your text. No AI reply is generated.</span> : null}
          <textarea value={draft} rows={3} disabled={busy} onChange={(event) => onDraft(event.target.value)} />
        </label>
        <button type="submit" className="primary" disabled={busy || !draft.trim()}>
          {sending ? "Sending…" : mode === "CUSTOMER" ? "Send customer message" : "Send manual reply"}
        </button>
      </form>
    </div>
  );
}
