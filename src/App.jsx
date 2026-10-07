import { useState, useCallback, useRef } from "react";
import { useTheme } from "./hooks/useTheme";
import * as apiService from "./services/apiService";

import Header from "./components/Header";
import UploadSection from "./components/UploadSection";
import ProcessingOverlay from "./components/ProcessingOverlay";
import GovernanceBadges from "./components/GovernanceBadges";
import KPICards from "./components/KPICards";
import SentimentChart from "./components/SentimentChart";
import TrendChart from "./components/TrendChart";
import ThemesList from "./components/ThemesList";
import VerbatimsDrawer from "./components/VerbatimsDrawer";

export default function App() {
  const { theme, toggleTheme } = useTheme();

  /* ── View state ───────────────────────────────────────────── */
  const [view, setView] = useState("upload"); // upload | processing | dashboard
  const [jobId, setJobId] = useState(null);

  /* ── Processing state ─────────────────────────────────────── */
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const pollRef = useRef(null);

  /* ── Dashboard data ───────────────────────────────────────── */
  const [analyticsData, setAnalyticsData] = useState(null);

  /* ── Drawer state ─────────────────────────────────────────── */
  const [selectedTheme, setSelectedTheme] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  /* ── Error state ──────────────────────────────────────────── */
  const [errorMsg, setErrorMsg] = useState("");

  /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     File Upload → Processing → Dashboard
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
  const handleFileSelected = useCallback(async (file) => {
    try {
      setView("processing");
      setProgress(0);
      setStatusMessage("Uploading file…");
      setErrorMsg("");

      // 1. Upload
      const uploadRes = await apiService.uploadFile(file);
      const jid = uploadRes.job_id;
      setJobId(jid);

      // 2. Poll for progress
      pollRef.current = window.setInterval(async () => {
        try {
          const status = await apiService.getJobStatus(jid);
          setProgress(status.progress);
          setStatusMessage(status.message);

          if (status.status === "COMPLETED") {
            window.clearInterval(pollRef.current);
            pollRef.current = null;

            // 3. Fetch analytics
            const summary = await apiService.getAnalyticsSummary(jid);
            setAnalyticsData(summary);
            setView("dashboard");
          } else if (status.status === "FAILED") {
            window.clearInterval(pollRef.current);
            pollRef.current = null;
            setErrorMsg("Processing failed. Please try again.");
            setView("upload");
          }
        } catch (err) {
          console.error("Polling error:", err);
        }
      }, 1200);
    } catch (err) {
      console.error("Upload error:", err);
      setErrorMsg("Upload failed. Please check your file and try again.");
      setView("upload");
    }
  }, []);

  /* ── Reset to upload ──────────────────────────────────────── */
  const handleReset = useCallback(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setView("upload");
    setJobId(null);
    setProgress(0);
    setStatusMessage("");
    setAnalyticsData(null);
    setSelectedTheme(null);
    setDrawerOpen(false);
  }, []);

  /* ── Theme drawer ─────────────────────────────────────────── */
  const handleThemeClick = useCallback((themeData) => {
    setSelectedTheme(themeData);
    setDrawerOpen(true);
  }, []);

  const handleDrawerClose = useCallback(() => {
    setDrawerOpen(false);
  }, []);

  /* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     Render
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
  return (
    <div className="app-wrapper">
      <Header
        theme={theme}
        toggleTheme={toggleTheme}
        showReset={view === "dashboard"}
        onReset={handleReset}
      />

      <main className="main-content">
        {/* ── Upload View ────────────────────────────────────── */}
        {view === "upload" && (
          <UploadSection onFileSelected={handleFileSelected} />
        )}

        {/* ── Processing View ────────────────────────────────── */}
        {view === "processing" && (
          <ProcessingOverlay progress={progress} statusMessage={statusMessage} />
        )}

        {/* ── Dashboard View ─────────────────────────────────── */}
        {view === "dashboard" && analyticsData && (
          <div className="dashboard">
            <GovernanceBadges summary={analyticsData.summary} />
            <KPICards
              summary={analyticsData.summary}
              breakdown={analyticsData.sentiment_breakdown}
            />
            <div className="charts-row">
              <SentimentChart
                breakdown={analyticsData.sentiment_breakdown}
                theme={theme}
              />
              <TrendChart jobId={jobId} theme={theme} />
            </div>
            <ThemesList
              themes={analyticsData.themes}
              onThemeClick={handleThemeClick}
            />
          </div>
        )}
      </main>

      {/* ── Verbatims Drawer ───────────────────────────────── */}
      <VerbatimsDrawer
        isOpen={drawerOpen}
        theme={selectedTheme}
        onClose={handleDrawerClose}
      />

      {/* ── Error Toast ────────────────────────────────────── */}
      <div className={`error-toast${errorMsg ? " visible" : ""}`} role="alert">
        {errorMsg}
      </div>
    </div>
  );
}
