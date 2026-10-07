import { Sun, Moon, RotateCcw } from "lucide-react";

export default function Header({ theme, toggleTheme, showReset, onReset }) {
  return (
    <header className="header">
      <div className="header-inner">
        <div className="header-brand">
          <div className="header-logo" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20V10"/>
              <path d="M18 20V4"/>
              <path d="M6 20v-4"/>
            </svg>
          </div>
          <div>
            <div className="header-title">Feedback Analyzer</div>
            <div className="header-subtitle">Enterprise Review Intelligence</div>
          </div>
        </div>

        <div className="header-actions">
          {showReset && (
            <button className="new-analysis-btn" onClick={onReset} title="Start new analysis">
              <RotateCcw size={14} />
              New Analysis
            </button>
          )}
          <button
            className="theme-toggle"
            onClick={toggleTheme}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </div>
    </header>
  );
}
