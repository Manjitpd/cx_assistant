import { useEffect, useRef, useState } from "react";
import { fetchConversation, fetchConversations, sendCustomerMessage, sendManualReply } from "../api";
import type { ConversationDetail, ConversationSummary, MessageAuthor } from "../types";

export function useInbox(brandId: string) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [mode, setMode] = useState<MessageAuthor>("AGENT");
  const [draft, setDraft] = useState("");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const sendLock = useRef(false);
  const idempotencyKey = useRef("");

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if (!brandId) {
      setConversations([]);
      setSelectedId("");
      setDetail(null);
      setLoadingList(false);
      return;
    }
    let cancelled = false;
    setLoadingList(true);
    setError("");
    setNotice("");
    setSelectedId("");
    setDetail(null);
    setDraft("");
    idempotencyKey.current = "";
    fetchConversations(brandId)
      .then((rows) => {
        if (cancelled) return;
        setConversations(rows);
        setSelectedId(rows[0]?.id ?? "");
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message);
      })
      .finally(() => {
        if (!cancelled) setLoadingList(false);
      });
    return () => {
      cancelled = true;
    };
  }, [brandId]);

  useEffect(() => {
    idempotencyKey.current = "";
    if (!brandId || !selectedId) {
      setDetail(null);
      setLoadingDetail(false);
      return;
    }
    let cancelled = false;
    setLoadingDetail(true);
    setDetail(null);
    fetchConversation(brandId, selectedId)
      .then((conversation) => {
        if (!cancelled) setDetail(conversation);
      })
      .catch((reason: Error) => {
        if (!cancelled) {
          setDetail(null);
          setError(reason.message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingDetail(false);
      });
    return () => {
      cancelled = true;
    };
  }, [brandId, selectedId]);

  function updateDraft(value: string) {
    idempotencyKey.current = "";
    setDraft(value);
  }

  async function send() {
    const body = draft.trim();
    if (!body) {
      setError("Enter a reply before sending.");
      return;
    }
    if (!brandId || !selectedId || sendLock.current) return;
    sendLock.current = true;
    setSending(true);
    setError("");
    setNotice("");
    const manual = mode === "AGENT";
    if (manual && !idempotencyKey.current) {
      idempotencyKey.current = crypto.randomUUID();
    }
    const key = idempotencyKey.current;
    try {
      const updated = manual
        ? await sendManualReply(brandId, selectedId, body, key)
        : await sendCustomerMessage(brandId, selectedId, body);
      setDetail(updated);
      setDraft("");
      idempotencyKey.current = "";
      setNotice(manual ? "Manual reply sent." : "Customer message sent.");
      setConversations(await fetchConversations(brandId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not send the message");
    } finally {
      sendLock.current = false;
      setSending(false);
    }
  }

  function replaceDetail(updated: ConversationDetail) {
    setDetail(updated);
    setError("");
    setNotice("Reply sent.");
    if (!brandId) return;
    void fetchConversations(brandId)
      .then(setConversations)
      .catch((reason: Error) => setError(reason.message));
  }

  return {
    conversations,
    selectedId,
    setSelectedId,
    detail,
    mode,
    setMode,
    draft,
    setDraft: updateDraft,
    loadingList,
    loadingDetail,
    sending,
    error,
    notice,
    send,
    replaceDetail,
  };
}
