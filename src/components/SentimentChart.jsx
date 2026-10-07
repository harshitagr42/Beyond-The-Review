import { useMemo } from "react";
import { Doughnut } from "react-chartjs-2";
import { Chart as ChartJS, ArcElement, Tooltip } from "chart.js";

ChartJS.register(ArcElement, Tooltip);

export default function SentimentChart({ breakdown, theme }) {
  if (!breakdown) return null;

  const isDark = theme === "dark";

  const data = useMemo(
    () => ({
      labels: ["Positive", "Neutral", "Negative"],
      datasets: [
        {
          data: [breakdown.positive, breakdown.neutral, breakdown.negative],
          backgroundColor: isDark
            ? ["#34d399", "#fbbf24", "#f87171"]
            : ["#059669", "#d97706", "#dc2626"],
          borderColor: isDark ? "#151d2e" : "#ffffff",
          borderWidth: 3,
          hoverOffset: 6,
          borderRadius: 4,
          spacing: 2,
        },
      ],
    }),
    [breakdown, isDark]
  );

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: true,
      cutout: "68%",
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: isDark ? "#1e293b" : "#ffffff",
          titleColor: isDark ? "#f1f5f9" : "#0f172a",
          bodyColor: isDark ? "#94a3b8" : "#475569",
          borderColor: isDark ? "rgba(99,102,241,0.2)" : "#e2e8f0",
          borderWidth: 1,
          cornerRadius: 8,
          padding: 12,
          bodyFont: { family: "Inter", size: 13 },
          titleFont: { family: "Inter", size: 13, weight: 600 },
          callbacks: {
            label: (ctx) => ` ${ctx.parsed}% of reviews`,
          },
        },
      },
      animation: {
        animateRotate: true,
        duration: 800,
        easing: "easeOutQuart",
      },
    }),
    [isDark]
  );

  const legendItems = [
    { label: "Positive", value: breakdown.positive, color: isDark ? "#34d399" : "#059669" },
    { label: "Neutral", value: breakdown.neutral, color: isDark ? "#fbbf24" : "#d97706" },
    { label: "Negative", value: breakdown.negative, color: isDark ? "#f87171" : "#dc2626" },
  ];

  return (
    <div className="chart-card stagger-6" id="sentiment-chart">
      <div className="chart-title">Sentiment Distribution</div>
      <div className="donut-chart-container">
        <Doughnut data={data} options={options} />
      </div>
      <div className="sentiment-legend">
        {legendItems.map((item) => (
          <div key={item.label} className="legend-item">
            <div className="legend-left">
              <div className="legend-dot" style={{ background: item.color }} />
              <span className="legend-label">{item.label}</span>
            </div>
            <span className="legend-value">{item.value}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
