import { useState, useCallback, useRef, useEffect } from "react";
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
  const pollInFlightRef = useRef(false);
  const pollFailuresRef = useRef(0);

  const clearPolling = useCallback(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    pollInFlightRef.current = false;
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

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
      clearPolling();
      pollFailuresRef.current = 0;
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
        if (pollInFlightRef.current) return;
        pollInFlightRef.current = true;
        try {
          const status = await apiService.getJobStatus(jid);
          pollFailuresRef.current = 0;
          setProgress(status.progress);
          setStatusMessage(status.message);

          if (status.status === "COMPLETED") {
            clearPolling();

            try {
              const summary = await apiService.getAnalyticsSummary(jid);
              setAnalyticsData(summary);
              setView("dashboard");
            } catch (summaryErr) {
              setErrorMsg(
                summaryErr.userMessage ||
                  "This analysis is no longer available. Please upload the file again."
              );
              setView("upload");
            }
          } else if (status.status === "FAILED") {
            clearPolling();
            setErrorMsg(
              status.error?.message || status.message || "Processing failed. Please try again."
            );
            setView("upload");
          }
        } catch (err) {
          if (err.status === 404) {
            clearPolling();
            setErrorMsg(
              err.userMessage ||
                "This analysis is no longer available. Please upload the file again."
            );
            setView("upload");
            return;
          }
          pollFailuresRef.current += 1;
          if (pollFailuresRef.current >= 5) {
            clearPolling();
            setErrorMsg(
              err.userMessage || "Cannot reach the server. Make sure the backend is running."
            );
            setView("upload");
          }
        } finally {
          pollInFlightRef.current = false;
        }
      }, 1200);
    } catch (err) {
      setErrorMsg(
        err.userMessage || "Upload failed. Please check your file and try again."
      );
      setView("upload");
    }
  }, [clearPolling]);

  /* ── Reset to upload ──────────────────────────────────────── */
  const handleReset = useCallback(() => {
    clearPolling();
    pollFailuresRef.current = 0;
    setView("upload");
    setJobId(null);
    setProgress(0);
    setStatusMessage("");
    setAnalyticsData(null);
    setSelectedTheme(null);
    setDrawerOpen(false);
    setErrorMsg("");
  }, [clearPolling]);

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
