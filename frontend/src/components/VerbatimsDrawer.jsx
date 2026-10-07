import { useEffect, useRef } from "react";
import { X, MessageCircle } from "lucide-react";

/**
 * Renders review text with [REDACTED] tags highlighted.
 */
function renderVerbatimText(text) {
  const parts = text.split(/(\[REDACTED\])/gi);
  return parts.map((part, i) => {
    if (part.toUpperCase() === "[REDACTED]") {
      return (
        <span key={i} className="pii-redacted">
          [REDACTED]
        </span>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export default function VerbatimsDrawer({ isOpen, theme, onClose }) {
  const panelRef = useRef(null);

  /* ── Close on Escape key ──────────────────────────────────── */
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [isOpen, onClose]);

  /* ── Lock body scroll when open ───────────────────────────── */
  useEffect(() => {
    document.body.style.overflow = isOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [isOpen]);

  /* ── Focus trap ───────────────────────────────────────────── */
  useEffect(() => {
    if (isOpen && panelRef.current) {
      panelRef.current.focus();
    }
  }, [isOpen]);

  if (!theme) return null;

  const verbatims = theme.sample_verbatims || [];

  return (
    <>
      {/* Backdrop */}
      <div
        className={`drawer-overlay${isOpen ? " open" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <aside
        ref={panelRef}
        className={`drawer-panel${isOpen ? " open" : ""}`}
        tabIndex={-1}
        role="dialog"
        aria-label={`Verbatims for ${theme.name}`}
        id="verbatims-drawer"
      >
        {/* Header */}
        <div className="drawer-header">
          <div className="drawer-header-info">
            <h2>{theme.name}</h2>
            <div className="drawer-header-meta">
              <span className="drawer-stat">
                <MessageCircle size={12} />
                <strong>{verbatims.length}</strong> verbatims shown
              </span>
              <span className="drawer-stat">
                Score: <strong>{theme.sentiment_score?.toFixed(2)}</strong>
              </span>
              <span className="drawer-stat">
                Sentiment: <strong>{theme.sentiment}</strong>
              </span>
            </div>
          </div>
          <button className="drawer-close" onClick={onClose} aria-label="Close drawer">
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="drawer-body">
          {verbatims.length === 0 ? (
            <p style={{ color: "var(--text-tertiary)", padding: "var(--space-8)", textAlign: "center" }}>
              No verbatims available for this theme.
            </p>
          ) : (
            verbatims.map((v) => (
              <div key={v.id} className="verbatim-card">
                <div className="verbatim-text">
                  {renderVerbatimText(v.text)}
                </div>
                <div className="verbatim-footer">
                  <span className={`verbatim-sentiment ${v.sentiment}`}>
                    {v.sentiment}
                  </span>
                  <span className="verbatim-id">{v.id}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </aside>
    </>
  );
}
