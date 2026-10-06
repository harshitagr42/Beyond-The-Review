import { BarChart3, TrendingDown, ThumbsUp, Minus, ThumbsDown } from "lucide-react";

export default function KPICards({ summary, breakdown }) {
  if (!summary || !breakdown) return null;

  const cards = [
    {
      label: "Total Reviews",
      value: summary.total_reviews.toLocaleString(),
      trend: summary.overall_sentiment,
      trendClass: "negative",
      iconClass: "indigo",
      icon: <BarChart3 size={16} />,
    },
    {
      label: "Net Sentiment",
      value: summary.net_sentiment_score > 0 ? `+${summary.net_sentiment_score}` : `${summary.net_sentiment_score}`,
      trend: "NSS",
      trendClass: summary.net_sentiment_score >= 0 ? "positive" : "negative",
      iconClass: "red",
      icon: <TrendingDown size={16} />,
      gradient: true,
    },
    {
      label: "Positive",
      value: `${breakdown.positive}%`,
      trend: `${Math.round(summary.total_reviews * breakdown.positive / 100).toLocaleString()} reviews`,
      trendClass: "positive",
      iconClass: "green",
      icon: <ThumbsUp size={16} />,
    },
    {
      label: "Neutral",
      value: `${breakdown.neutral}%`,
      trend: `${Math.round(summary.total_reviews * breakdown.neutral / 100).toLocaleString()} reviews`,
      trendClass: "",
      iconClass: "amber",
      icon: <Minus size={16} />,
    },
    {
      label: "Negative",
      value: `${breakdown.negative}%`,
      trend: `${Math.round(summary.total_reviews * breakdown.negative / 100).toLocaleString()} reviews`,
      trendClass: "negative",
      iconClass: "red",
      icon: <ThumbsDown size={16} />,
    },
  ];

  return (
    <div className="kpi-grid" id="kpi-cards">
      {cards.map((card, i) => (
        <div key={card.label} className={`kpi-card stagger-${i + 1}`}>
          <div className="kpi-header">
            <span className="kpi-label">{card.label}</span>
            <div className={`kpi-icon ${card.iconClass}`}>{card.icon}</div>
          </div>
          <div className={`kpi-value${card.gradient ? " gradient-text" : ""}`}>{card.value}</div>
          <div className={`kpi-trend ${card.trendClass}`}>{card.trend}</div>
        </div>
      ))}
    </div>
  );
}
