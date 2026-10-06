import { useEffect, useState } from "react";
import { fetchBrands } from "./api";
import { ContextPanel } from "./components/ContextPanel";
import { ConversationList } from "./components/ConversationList";
import { ConversationThread } from "./components/ConversationThread";
import { useInbox } from "./hooks/useInbox";
import { KnowledgePage } from "./pages/KnowledgePage";
import type { Brand } from "./types";

type Section = "conversations" | "knowledge" | "brands";

export function App() {
  const [section, setSection] = useState<Section>("conversations");
  const [brands, setBrands] = useState<Brand[]>([]);
  const [brandId, setBrandId] = useState("");
  const [brandsLoading, setBrandsLoading] = useState(true);
  const [brandsError, setBrandsError] = useState("");
  const [brandNotice, setBrandNotice] = useState("");
  const inbox = useInbox(brandId);
  const selectedBrand = brands.find((brand) => brand.id === brandId);

  useEffect(() => {
    let cancelled = false;
    fetchBrands()
      .then((nextBrands) => {
        if (cancelled) return;
        setBrands(nextBrands);
        setBrandId(nextBrands[0]?.id ?? "");
      })
      .catch((reason: Error) => {
        if (!cancelled) setBrandsError(reason.message);
      })
      .finally(() => {
        if (!cancelled) setBrandsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!brandNotice) return;
    const timer = window.setTimeout(() => setBrandNotice(""), 3200);
    return () => window.clearTimeout(timer);
  }, [brandNotice]);

  function chooseBrand(nextBrandId: string) {
    const brand = brands.find((item) => item.id === nextBrandId);
    setBrandId(nextBrandId);
    if (brand) setBrandNotice(`${brand.name} is the current brand.`);
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="mark" aria-hidden="true">
            CX
          </span>
          <div>
            <p className="product-name">Datastraw CX</p>
            <button type="button" className="brand-switch" onClick={() => setSection("brands")}>
              <span>{selectedBrand?.name ?? (brandsLoading ? "Loading brand…" : "No brand selected")}</span>
              <span className="brand-switch-action">Switch</span>
            </button>
          </div>
        </div>
        <nav className="nav-list" aria-label="Sections">
          <button
            type="button"
            className={section === "conversations" ? "selected" : ""}
            aria-current={section === "conversations" ? "page" : undefined}
            onClick={() => setSection("conversations")}
          >
            Conversations
          </button>
          <button
            type="button"
            className={section === "knowledge" ? "selected" : ""}
            aria-current={section === "knowledge" ? "page" : undefined}
            onClick={() => setSection("knowledge")}
          >
            Knowledge base
          </button>
          <button
            type="button"
            className={section === "brands" ? "selected" : ""}
            aria-current={section === "brands" ? "page" : undefined}
            onClick={() => setSection("brands")}
          >
            Brands
          </button>
        </nav>
      </header>

      <div className={section === "conversations" ? "shell with-inbox" : "shell solo"}>
        {section === "conversations" ? (
          <aside className="rail">
            <ConversationList
              conversations={inbox.conversations}
              selectedId={inbox.selectedId}
              loading={brandsLoading || inbox.loadingList}
              onSelect={inbox.setSelectedId}
            />
          </aside>
        ) : null}

        <main className="stage">
          {brandsError ? (
            <p className="banner" role="alert">
              {brandsError}
            </p>
          ) : null}
          {section === "conversations" ? (
            <>
              {inbox.error ? (
                <p className="banner" role="alert">
                  {inbox.error}
                </p>
              ) : null}
              <ConversationThread
                detail={inbox.detail}
                loading={inbox.loadingDetail}
                sending={inbox.sending}
                notice={inbox.notice}
                mode={inbox.mode}
                draft={inbox.draft}
                onMode={inbox.setMode}
                onDraft={inbox.setDraft}
                onSend={() => void inbox.send()}
              />
            </>
          ) : null}
          {section === "knowledge" ? (
            <KnowledgePage brandId={brandId} brandName={selectedBrand?.name ?? ""} />
          ) : null}
          {section === "brands" ? (
            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2>Brands</h2>
                  <p>Choose the brand whose conversations and policies are shown.</p>
                </div>
              </div>
              {brandNotice ? (
                <p className="notice" role="status">
                  {brandNotice}
                </p>
              ) : null}
              {brandsLoading ? (
                <div className="loading-state" role="status">
                  <span className="skeleton" />
                  <span className="skeleton short" />
                  <p>Loading brands…</p>
                </div>
              ) : null}
              {!brandsLoading && brands.length === 0 ? (
                <div className="empty-state">
                  <p className="empty-title">No brands yet</p>
                  <p>Brands appear here after they are added to the workspace.</p>
                </div>
              ) : null}
              <ul className="brand-list">
                {brands.map((brand) => (
                  <li key={brand.id}>
                    <button
                      type="button"
                      className={brand.id === brandId ? "thread selected" : "thread"}
                      onClick={() => chooseBrand(brand.id)}
                    >
                      <span className="avatar" aria-hidden="true">
                        {brand.name.slice(0, 1)}
                      </span>
                      <span className="thread-copy">
                        <strong>{brand.name}</strong>
                        <span>{brand.slug}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </main>

        <aside className="inspector" aria-label="Conversation context">
          {section === "conversations" ? (
            <ContextPanel detail={inbox.detail} loading={inbox.loadingDetail} onSent={inbox.replaceDetail} />
          ) : (
            <section className="case-card">
              <h2>Brand</h2>
              {selectedBrand ? (
                <>
                  <p className="fact-name">{selectedBrand.name}</p>
                  <p>{selectedBrand.slug}</p>
                </>
              ) : (
                <p className="muted">No brand selected.</p>
              )}
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
