import { useMemo, useState, useEffect } from "react";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from "chart.js";
import * as apiService from "../services/apiService";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend);

export default function TrendChart({ jobId, theme }) {
  const [interval, setInterval] = useState("weekly");
  const [trendData, setTrendData] = useState(null);

  const isDark = theme === "dark";

  useEffect(() => {
    let cancelled = false;
    apiService.getTrends(jobId, interval).then((d) => {
      if (!cancelled) setTrendData(d);
    });
    return () => { cancelled = true; };
  }, [jobId, interval]);

  const chartData = useMemo(() => {
    if (!trendData) return null;

    const makeGradient = (ctx, color, alpha) => {
      const gradient = ctx.chart.ctx.createLinearGradient(0, 0, 0, ctx.chart.height);
      gradient.addColorStop(0, `${color}${alpha}`);
      gradient.addColorStop(1, `${color}00`);
      return gradient;
    };

    return {
      labels: trendData.labels,
      datasets: [
        {
          label: "Positive",
          data: trendData.positive,
          borderColor: isDark ? "#34d399" : "#059669",
          backgroundColor: (ctx) => makeGradient(ctx, isDark ? "#34d399" : "#059669", "20"),
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBorderWidth: 2,
          pointHoverBorderColor: isDark ? "#151d2e" : "#ffffff",
          borderWidth: 2.5,
        },
        {
          label: "Neutral",
          data: trendData.neutral,
          borderColor: isDark ? "#fbbf24" : "#d97706",
          backgroundColor: (ctx) => makeGradient(ctx, isDark ? "#fbbf24" : "#d97706", "15"),
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBorderWidth: 2,
          pointHoverBorderColor: isDark ? "#151d2e" : "#ffffff",
          borderWidth: 2.5,
        },
        {
          label: "Negative",
          data: trendData.negative,
          borderColor: isDark ? "#f87171" : "#dc2626",
          backgroundColor: (ctx) => makeGradient(ctx, isDark ? "#f87171" : "#dc2626", "18"),
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBorderWidth: 2,
          pointHoverBorderColor: isDark ? "#151d2e" : "#ffffff",
          borderWidth: 2.5,
        },
      ],
    };
  }, [trendData, isDark]);

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          display: true,
          position: "top",
          align: "end",
          labels: {
            color: isDark ? "#94a3b8" : "#475569",
            font: { family: "Inter", size: 11, weight: 500 },
            boxWidth: 12,
            boxHeight: 3,
            borderRadius: 2,
            useBorderRadius: true,
            padding: 16,
          },
        },
        tooltip: {
          backgroundColor: isDark ? "#1e293b" : "#ffffff",
          titleColor: isDark ? "#f1f5f9" : "#0f172a",
          bodyColor: isDark ? "#94a3b8" : "#475569",
          borderColor: isDark ? "rgba(99,102,241,0.2)" : "#e2e8f0",
          borderWidth: 1,
          cornerRadius: 8,
          padding: 12,
          bodyFont: { family: "Inter", size: 12 },
          titleFont: { family: "Inter", size: 12, weight: 600 },
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y}%`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: isDark ? "rgba(148,163,184,0.06)" : "rgba(0,0,0,0.04)", drawBorder: false },
          ticks: {
            color: isDark ? "#64748b" : "#94a3b8",
            font: { family: "Inter", size: 10 },
            maxRotation: 45,
          },
          border: { display: false },
        },
        y: {
          min: 0,
          max: 80,
          grid: { color: isDark ? "rgba(148,163,184,0.06)" : "rgba(0,0,0,0.04)", drawBorder: false },
          ticks: {
            color: isDark ? "#64748b" : "#94a3b8",
            font: { family: "Inter", size: 10 },
            callback: (v) => `${v}%`,
            stepSize: 20,
          },
          border: { display: false },
        },
      },
      animation: {
        duration: 1000,
        easing: "easeOutQuart",
      },
    }),
    [isDark]
  );

  return (
    <div className="chart-card stagger-7" id="trend-chart">
      <div className="chart-title">
        <span>Sentiment Over Time</span>
        <div className="chart-title-actions">
          <button
            className={`interval-btn${interval === "weekly" ? " active" : ""}`}
            onClick={() => setInterval("weekly")}
          >
            Weekly
          </button>
          <button
            className={`interval-btn${interval === "monthly" ? " active" : ""}`}
            onClick={() => setInterval("monthly")}
          >
            Monthly
          </button>
        </div>
      </div>
      <div className="trend-chart-container">
        {chartData ? (
          <Line data={chartData} options={options} />
        ) : (
          <div className="skeleton" style={{ width: "100%", height: "100%" }} />
        )}
      </div>
    </div>
  );
}
