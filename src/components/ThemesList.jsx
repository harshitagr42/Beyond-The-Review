import { MessageSquareText, ChevronRight } from "lucide-react";

/**
 * Maps sentiment label to CSS modifier class.
 */
function sentimentClass(sentiment) {
  const s = sentiment?.toLowerCase() || "";
  if (s.includes("strongly negative")) return "strongly-negative";
  if (s.includes("negative")) return "negative";
  if (s.includes("positive")) return "positive";
  return "neutral";
}

/**
 * Computes the visual width of the sentiment score bar.
 * Score ranges from -1 (fully negative) to +1 (fully positive).
 * We map to 0–100% width for the negative side.
 */
function scoreToWidth(score) {
  return Math.min(100, Math.round(Math.abs(score) * 100));
}

function scoreToColor(score) {
  if (score <= -0.7) return "var(--color-negative)";
  if (score <= -0.4) return "#fb923c";
  if (score <= 0) return "var(--color-neutral-sentiment)";
  return "var(--color-positive)";
}

export default function ThemesList({ themes, onThemeClick }) {
  if (!themes || themes.length === 0) return null;

  return (
    <section className="themes-section" id="themes-list">
      <div className="dashboard-section-title">
        <MessageSquareText size={14} />
        Complaint Themes — Ranked by Volume
      </div>
      <div className="themes-grid">
        {themes.map((theme, index) => (
          <div
            key={theme.id}
            className={`theme-card stagger-${Math.min(index + 1, 8)}`}
            onClick={() => onThemeClick(theme)}
            tabIndex={0}
            role="button"
            aria-label={`View verbatims for ${theme.name}`}
            onKeyDown={(e) => { if (e.key === "Enter") onThemeClick(theme); }}
          >
            <div className="theme-card-header">
              <span className="theme-rank">#{index + 1}</span>
              <span className={`theme-sentiment-pill ${sentimentClass(theme.sentiment)}`}>
                {theme.sentiment}
              </span>
            </div>
            <div className="theme-name">{theme.name}</div>
            <div className="theme-meta">
              <span className="theme-meta-item">
                <strong>{theme.count.toLocaleString()}</strong> reviews
              </span>
              <span className="theme-meta-item">
                Score: <strong>{theme.sentiment_score.toFixed(2)}</strong>
              </span>
            </div>
            <div className="theme-score-bar">
              <div
                className="theme-score-fill"
                style={{
                  width: `${scoreToWidth(theme.sentiment_score)}%`,
                  background: scoreToColor(theme.sentiment_score),
                }}
              />
            </div>
            {theme.sample_verbatims?.[0] && (
              <div className="theme-preview">
                "{theme.sample_verbatims[0].text}"
              </div>
            )}
            <div className="theme-view-more">
              View all verbatims <ChevronRight size={14} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
