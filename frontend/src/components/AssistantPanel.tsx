import { useEffect, useRef, useState } from "react";
import { approveGeneration, editGeneration, fetchConversation, generateReply, sendGeneration } from "../api";
import { GenerationHistory } from "./GenerationHistory";
import {
  CATEGORY_LABEL,
  type ConversationDetail,
  type EvidenceStatus,
  type GenerationState,
  type GenerationStatus,
  type RetrievedKnowledge,
} from "../types";

type AssistantPanelProps = {
  brandId: string;
  conversationId: string;
  customerMessage: string | null;
  disabled: boolean;
  onSent: (detail: ConversationDetail) => void;
};

type StepPhase = "done" | "current" | "waiting" | "optional";

const EVIDENCE_LABEL: Record<EvidenceStatus, string> = {
  SUPPORTED: "Supported",
  PARTIALLY_SUPPORTED: "Partially supported",
  INSUFFICIENT_INFORMATION: "Insufficient information",
  HUMAN_REVIEW_REQUIRED: "Human review required",
};

const EVIDENCE_CLASS: Record<EvidenceStatus, string> = {
  SUPPORTED: "supported",
  PARTIALLY_SUPPORTED: "partial",
  INSUFFICIENT_INFORMATION: "insufficient",
  HUMAN_REVIEW_REQUIRED: "review",
};

const WORKFLOW_LABEL: Record<GenerationStatus, string> = {
  AI_GENERATED: "AI generated",
  EDITED: "Edited",
  APPROVED: "Approved",
  SENT: "Sent",
};

export function AssistantPanel({ brandId, conversationId, customerMessage, disabled, onSent }: AssistantPanelProps) {
  const [pending, setPending] = useState("");
  const [draft, setDraft] = useState("");
  const [original, setOriginal] = useState("");
  const [edited, setEdited] = useState<string | null>(null);
  const [knowledge, setKnowledge] = useState<RetrievedKnowledge[]>([]);
  const [evidence, setEvidence] = useState<EvidenceStatus | null>(null);
  const [workflow, setWorkflow] = useState<GenerationStatus | null>(null);
  const [generationId, setGenerationId] = useState("");
  const [warning, setWarning] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const request = useRef(0);
  const busy = pending !== "" || disabled;
  const savedText = edited ?? original;
  const dirty = workflow !== null && draft.trim() !== savedText.trim();
  const sent = workflow === "SENT";

  useEffect(() => {
    request.current += 1;
    setPending("");
    setDraft("");
    setOriginal("");
    setEdited(null);
    setKnowledge([]);
    setEvidence(null);
    setWorkflow(null);
    setGenerationId("");
    setWarning("");
    setError("");
    setNotice("");
  }, [conversationId]);

  function applyState(state: GenerationState) {
    setGenerationId(state.id);
    setWorkflow(state.status);
    setOriginal(state.suggested_reply);
    setEdited(state.edited_reply);
    setEvidence(state.evidence_status);
    setWarning(state.warning ?? "");
    setDraft(state.status === "SENT" ? (state.final_reply ?? state.edited_reply ?? state.suggested_reply) : (state.edited_reply ?? state.suggested_reply));
  }

  async function generate() {
    const ticket = ++request.current;
    setPending("generate");
    setError("");
    setNotice("");
    try {
      const result = await generateReply(conversationId);
      if (ticket !== request.current) return;
      setGenerationId(result.generation_id);
      setWorkflow(result.status);
      setOriginal(result.suggested_reply);
      setEdited(null);
      setDraft(result.suggested_reply);
      setKnowledge(result.retrieved_knowledge);
      setEvidence(result.evidence_status);
      setWarning(result.warning ?? "");
    } catch (reason) {
      if (ticket !== request.current) return;
      setError(reason instanceof Error ? reason.message : "Could not generate a reply");
    } finally {
      if (ticket === request.current) setPending("");
    }
  }

  async function saveEdit() {
    const body = draft.trim();
    if (!generationId || !body || !dirty || sent) return;
    const ticket = ++request.current;
    setPending("edit");
    setError("");
    setNotice("");
    try {
      const state = await editGeneration(generationId, body);
      if (ticket !== request.current) return;
      applyState(state);
      setNotice(state.status === "EDITED" ? "Edits saved." : "Draft matches the original AI response.");
    } catch (reason) {
      if (ticket !== request.current) return;
      setError(reason instanceof Error ? reason.message : "Could not save the edit");
    } finally {
      if (ticket === request.current) setPending("");
    }
  }

  async function approve() {
    if (!generationId || dirty || sent || workflow === "APPROVED") return;
    const ticket = ++request.current;
    setPending("approve");
    setError("");
    setNotice("");
    try {
      const state = await approveGeneration(generationId);
      if (ticket !== request.current) return;
      applyState(state);
      setNotice("Draft approved. It has not been sent.");
    } catch (reason) {
      if (ticket !== request.current) return;
      setError(reason instanceof Error ? reason.message : "Could not approve the draft");
    } finally {
      if (ticket === request.current) setPending("");
    }
  }

  async function send() {
    if (!generationId || workflow !== "APPROVED" || dirty) return;
    const ticket = ++request.current;
    setPending("send");
    setError("");
    setNotice("");
    try {
      await sendGeneration(generationId);
      if (ticket !== request.current) return;
      setWorkflow("SENT");
      setDraft(draft.trim());
      setNotice("Reply sent.");
      try {
        const updated = await fetchConversation(brandId, conversationId);
        if (ticket === request.current) onSent(updated);
      } catch (reason) {
        if (ticket !== request.current) return;
        setError(reason instanceof Error ? reason.message : "Reply sent, but the conversation could not be refreshed");
      }
    } catch (reason) {
      if (ticket !== request.current) return;
      setError(reason instanceof Error ? reason.message : "Could not send the reply");
    } finally {
      if (ticket === request.current) setPending("");
    }
  }

  const generating = pending === "generate";
  const generated = workflow !== null && !generating;
  const approved = generated && (workflow === "APPROVED" || workflow === "SENT");
  const editDone = generated && (edited !== null || workflow === "EDITED" || approved);
  const editOptional = generated && !dirty && workflow === "AI_GENERATED" && edited === null;
  const steps: { label: string; phase: StepPhase }[] = [
    { label: "Customer message", phase: customerMessage ? "done" : "current" },
    {
      label: "Generate reply",
      phase: generating ? "current" : generated ? "done" : customerMessage ? "current" : "waiting",
    },
    { label: "Retrieved knowledge", phase: generating ? "current" : generated ? "done" : "waiting" },
    { label: "AI draft", phase: generated ? "done" : "waiting" },
    {
      label: "Edit",
      phase: generating ? "waiting" : dirty ? "current" : editDone ? "done" : editOptional ? "optional" : "waiting",
    },
    { label: "Approve", phase: approved ? "done" : generated && !dirty ? "current" : "waiting" },
    {
      label: "Send",
      phase: generated && workflow === "SENT" ? "done" : workflow === "APPROVED" && !dirty && !generating ? "current" : "waiting",
    },
    { label: "Conversation history", phase: generated && workflow === "SENT" ? "done" : "waiting" },
  ];
  const workflowClass =
    workflow === "AI_GENERATED" ? "generated" : workflow === "EDITED" ? "edited" : workflow === "APPROVED" ? "approved" : "sent";
  const nextGenerate = !workflow && !generating;
  const nextEdit = Boolean(workflow) && dirty && !sent && !generating;
  const nextApprove = Boolean(workflow) && !dirty && workflow !== "APPROVED" && workflow !== "SENT" && !generating;
  const nextSend = workflow === "APPROVED" && !dirty && !generating;

  return (
    <section className="reply-panel" aria-busy={pending !== ""}>
      <p className="eyebrow">Reply workflow</p>
      <h2>Draft and send</h2>
      <ol className="steps" aria-label="Reply steps">
        {steps.map((step, index) => (
          <li key={step.label} className={step.phase} aria-current={step.phase === "current" ? "step" : undefined}>
            <span className="step-index">{index + 1}</span>
            {step.label}
            {step.phase === "optional" ? " · optional" : ""}
          </li>
        ))}
      </ol>

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

      <section className="workflow-block">
        <h3>Customer message</h3>
        {customerMessage ? (
          <p className="customer-quote">{customerMessage}</p>
        ) : (
          <div className="empty-state">
            <p className="empty-title">No customer message</p>
            <p>The latest customer message is shown here when the conversation has one.</p>
          </div>
        )}
      </section>

      <section className="workflow-block">
        <h3>Generate reply</h3>
        <button type="button" className={nextGenerate ? "primary" : undefined} disabled={busy} onClick={() => void generate()}>
          {pending === "generate" ? "Generating…" : workflow ? "Regenerate" : "Generate Reply"}
        </button>
        {generating ? (
          <div className="loading-state" role="status">
            <span className="skeleton" />
            <span className="skeleton short" />
            <p>Retrieving knowledge and drafting a reply…</p>
          </div>
        ) : null}
      </section>

      <section className="workflow-block">
        <h3>Retrieved knowledge</h3>
        {generating && knowledge.length === 0 ? <p className="block-note">Retrieving knowledge…</p> : null}
        {generated && knowledge.length === 0 ? (
          <div className="empty-state">
            <p className="empty-title">No knowledge retrieved</p>
            <p>No policy from this brand matched the latest customer message.</p>
          </div>
        ) : null}
        {!workflow && !generating ? (
          <div className="empty-state">
            <p className="empty-title">Knowledge appears after generation</p>
            <p>Generate a reply to retrieve this brand’s policies for the customer message.</p>
          </div>
        ) : null}
        {knowledge.length > 0 ? (
          <ul className="knowledge-hits">
            {knowledge.map((entry) => (
              <li key={entry.knowledge_entry_id}>
                <div className="policy-meta">
                  <span className="category">{CATEGORY_LABEL[entry.category]}</span>
                  <span className="muted">Relevance {entry.score.toFixed(2)}</span>
                </div>
                <strong>{entry.title}</strong>
                <p>{entry.content}</p>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="workflow-block">
        <div className="draft-heading">
          <h3>AI draft</h3>
          {workflow ? <span className="draft-badge">Draft</span> : null}
        </div>
        {generating ? <p className="block-note">Generating a draft…</p> : null}
        {workflow ? (
          <>
            <p className="block-note">Approval</p>
            <p className={`workflow-status ${workflowClass}`}>{WORKFLOW_LABEL[workflow]}</p>
            {evidence ? <p className={`evidence-status ${EVIDENCE_CLASS[evidence]}`}>{EVIDENCE_LABEL[evidence]}</p> : null}
            {pending !== "generate" && warning ? <p className="warning-note">{warning}</p> : null}
            <h3>Original AI response</h3>
            <p className="original-reply">{original}</p>
            <label>
              {sent ? "Final response" : edited ? "Edited reply" : "Draft reply"}
              <textarea value={draft} rows={5} disabled={busy || sent} onChange={(event) => setDraft(event.target.value)} />
            </label>
            {dirty ? <p className="block-note">Unsaved edits. Save them before approving.</p> : null}
            {sent ? <p className="block-note">This response has been sent and appears in the conversation history.</p> : null}
          </>
        ) : (
          !generating && (
            <div className="empty-state">
              <p className="empty-title">No AI draft yet</p>
              <p>The draft stays here so you can edit it, approve it, and then send it.</p>
            </div>
          )
        )}
        <div className="assistant-actions">
          <button
            type="button"
            className={nextEdit ? "primary" : undefined}
            disabled={busy || !workflow || !dirty || sent}
            onClick={() => void saveEdit()}
          >
            {pending === "edit" ? "Saving…" : "Edit"}
          </button>
          <button
            type="button"
            className={nextApprove ? "primary" : undefined}
            disabled={busy || !workflow || dirty || sent || workflow === "APPROVED"}
            onClick={() => void approve()}
          >
            {pending === "approve" ? "Approving…" : "Approve"}
          </button>
          <button
            type="button"
            className={nextSend ? "primary" : undefined}
            disabled={busy || workflow !== "APPROVED" || dirty}
            onClick={() => void send()}
          >
            {pending === "send" ? "Sending…" : "Send"}
          </button>
        </div>
        {!sent ? (
          <p className="block-note">Approve does not send the reply. Send adds it to the conversation history.</p>
        ) : null}
      </section>

      <GenerationHistory brandId={brandId} conversationId={conversationId} />
    </section>
  );
}
