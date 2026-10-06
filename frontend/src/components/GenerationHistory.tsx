import { useEffect, useState } from "react";
import { fetchGenerationLogs } from "../api";
import { formatWhen } from "../format";
import { CATEGORY_LABEL, type Category, type GenerationLog } from "../types";

type GenerationHistoryProps = {
  brandId: string;
  conversationId: string;
};

function categoryLabel(category: string): string {
  return category in CATEGORY_LABEL ? CATEGORY_LABEL[category as Category] : category;
}

function visibleText(value: string | null): string {
  if (!value) return "";
  if (/bearer\s+\S+|sk-[A-Za-z0-9]|api[_-]?key/i.test(value)) {
    return "Provider error details were withheld.";
  }
  return value;
}

export function GenerationHistory({ brandId, conversationId }: GenerationHistoryProps) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<GenerationLog[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setError("");
    fetchGenerationLogs(brandId, conversationId)
      .then((logs) => {
        if (!cancelled) setRows(logs);
      })
      .catch((reason: Error) => {
        if (!cancelled) {
          setRows(null);
          setError(reason.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, brandId, conversationId]);

  return (
    <details
      className="generation-history"
      onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)}
    >
      <summary>Generation history</summary>
      {error ? (
        <p className="banner" role="alert">
          {error}
        </p>
      ) : null}
      {open && rows === null && !error ? (
        <div className="loading-state" role="status">
          <span className="skeleton" />
          <span className="skeleton short" />
          <p>Loading generation history…</p>
        </div>
      ) : null}
      {rows && rows.length === 0 ? (
        <div className="empty-state">
          <p className="empty-title">No generations yet</p>
          <p>AI drafts for this conversation are stored here after you generate one.</p>
        </div>
      ) : null}
      {rows && rows.length > 0 ? (
        <ol className="generation-log">
          {rows.map((row) => (
            <li key={row.id} className="log-card">
              <p className="muted">
                {formatWhen(row.created_at)}
                {row.model_name ? ` · ${row.model_name}` : ""}
                {row.latency_ms !== null ? ` · ${row.latency_ms} ms` : ""}
                {row.total_tokens !== null ? ` · ${row.total_tokens} tokens` : ""}
              </p>
              <p>
                {row.status} · {row.evidence_status}
              </p>
              <p>
                <strong>Original AI response</strong>
              </p>
              <p>{visibleText(row.suggested_reply)}</p>
              {row.edited_reply ? (
                <>
                  <p>
                    <strong>Edited response</strong>
                  </p>
                  <p>{visibleText(row.edited_reply)}</p>
                </>
              ) : null}
              {row.final_reply ? (
                <>
                  <p>
                    <strong>Final response</strong>
                  </p>
                  <p>{visibleText(row.final_reply)}</p>
                </>
              ) : null}
              {row.warning ? <p className="warning-note">{visibleText(row.warning)}</p> : null}
              {row.error_detail ? <p className="warning-note">{visibleText(row.error_detail)}</p> : null}
              {row.retrieved_context.length > 0 ? (
                <ul>
                  {row.retrieved_context.map((entry) => (
                    <li key={entry.knowledge_entry_id}>
                      {categoryLabel(entry.category)} · {entry.title}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">No retrieved policies were stored.</p>
              )}
            </li>
          ))}
        </ol>
      ) : null}
    </details>
  );
}
