import { useCallback, useEffect, useState } from "react";
import {
  createKnowledge,
  deleteKnowledge,
  fetchKnowledge,
  updateKnowledge,
} from "../api";
import {
  CATEGORIES,
  CATEGORY_LABEL,
  type Category,
  type KnowledgeDraft,
  type KnowledgeEntry,
} from "../types";

const EMPTY_DRAFT: KnowledgeDraft = {
  title: "",
  category: "RETURN",
  content: "",
  active: true,
};

type KnowledgePageProps = {
  brandId: string;
  brandName: string;
};

export function KnowledgePage({ brandId, brandName }: KnowledgePageProps) {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editor, setEditor] = useState<{ id: string | null; draft: KnowledgeDraft } | null>(null);
  const [pendingDelete, setPendingDelete] = useState<KnowledgeEntry | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");

  const loadEntries = useCallback(async (nextBrandId: string) => {
    setEntries(await fetchKnowledge(nextBrandId));
  }, []);

  useEffect(() => {
    if (!brandId) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setNotice("");
    loadEntries(brandId)
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [brandId, loadEntries]);

  async function saveDraft() {
    if (!brandId || !editor) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      if (editor.id) {
        await updateKnowledge(brandId, editor.id, editor.draft);
      } else {
        await createKnowledge(brandId, editor.draft);
      }
      setEditor(null);
      setNotice(editor.id ? "Policy updated." : "Policy created.");
      await loadEntries(brandId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save the policy");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(entry: KnowledgeEntry) {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await updateKnowledge(brandId, entry.id, {
        title: entry.title,
        category: entry.category,
        content: entry.content,
        active: !entry.active,
      });
      setNotice(entry.active ? "Policy disabled." : "Policy enabled.");
      await loadEntries(brandId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update the policy");
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await deleteKnowledge(brandId, pendingDelete.id);
      setPendingDelete(null);
      setNotice("Policy deleted.");
      await loadEntries(brandId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete the policy");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>{brandName || "Policies"}</h2>
          <p>{entries.filter((entry) => entry.active).length} active policies</p>
        </div>
        <button
          type="button"
          className="primary"
          disabled={!brandId || saving}
          onClick={() => setEditor({ id: null, draft: { ...EMPTY_DRAFT } })}
        >
          New policy
        </button>
      </div>

      {error ? (
        <p className="banner" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="notice" role="status">
          {notice}
        </p>
      ) : null}
      {loading ? (
        <div className="loading-state" role="status">
          <span className="skeleton" />
          <span className="skeleton short" />
          <p>Loading policies…</p>
        </div>
      ) : null}
      {!loading && entries.length === 0 ? (
        <div className="empty-state">
          <p className="empty-title">No policies yet</p>
          <p>This brand has no policies. New policy adds one for this brand only.</p>
        </div>
      ) : null}

      {entries.length > 0 ? (
        <ul className="policies">
          {entries.map((entry) => (
            <li key={entry.id} className={entry.active ? "policy" : "policy inactive"}>
              <div className="policy-main">
                <div className="policy-meta">
                  <span className="category">{CATEGORY_LABEL[entry.category]}</span>
                  <span className={entry.active ? "status on" : "status off"}>
                    {entry.active ? "Active" : "Disabled"}
                  </span>
                </div>
                <h3>{entry.title}</h3>
                <p>{entry.content}</p>
              </div>
              <div className="policy-actions">
                <button type="button" disabled={saving} onClick={() => void toggleActive(entry)}>
                  {entry.active ? "Disable" : "Enable"}
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() =>
                    setEditor({
                      id: entry.id,
                      draft: {
                        title: entry.title,
                        category: entry.category,
                        content: entry.content,
                        active: entry.active,
                      },
                    })
                  }
                >
                  Edit
                </button>
                <button type="button" className="danger" disabled={saving} onClick={() => setPendingDelete(entry)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {editor ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setEditor(null)}>
          <form
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="policy-form-title"
            onClick={(event) => event.stopPropagation()}
            onSubmit={(event) => {
              event.preventDefault();
              void saveDraft();
            }}
          >
            <h2 id="policy-form-title">{editor.id ? "Edit policy" : "New policy"}</h2>
            <label>
              Title
              <input
                value={editor.draft.title}
                maxLength={200}
                required
                onChange={(event) =>
                  setEditor({ ...editor, draft: { ...editor.draft, title: event.target.value } })
                }
              />
            </label>
            <label>
              Category
              <select
                value={editor.draft.category}
                onChange={(event) =>
                  setEditor({
                    ...editor,
                    draft: { ...editor.draft, category: event.target.value as Category },
                  })
                }
              >
                {CATEGORIES.map((category) => (
                  <option key={category} value={category}>
                    {CATEGORY_LABEL[category]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Content
              <textarea
                value={editor.draft.content}
                required
                rows={8}
                onChange={(event) =>
                  setEditor({ ...editor, draft: { ...editor.draft, content: event.target.value } })
                }
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={editor.draft.active}
                onChange={(event) =>
                  setEditor({ ...editor, draft: { ...editor.draft, active: event.target.checked } })
                }
              />
              Active
            </label>
            <div className="modal-actions">
              <button type="button" onClick={() => setEditor(null)}>
                Cancel
              </button>
              <button type="submit" className="primary" disabled={saving}>
                {saving ? "Saving…" : "Save policy"}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {pendingDelete ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setPendingDelete(null)}>
          <div
            className="modal confirm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-title"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="delete-title">Delete this policy?</h2>
            <p>
              {pendingDelete.title} will be removed from {brandName}. This does not affect the other brand.
            </p>
            <div className="modal-actions">
              <button type="button" onClick={() => setPendingDelete(null)}>
                Cancel
              </button>
              <button type="button" className="danger" disabled={saving} onClick={() => void confirmDelete()}>
                {saving ? "Deleting…" : "Delete policy"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
