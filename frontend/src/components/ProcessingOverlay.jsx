export default function ProcessingOverlay({ progress, statusMessage }) {
  return (
    <section className="processing-section" id="processing-section">
      <div className="processing-card">
        <div className="processing-spinner" aria-hidden="true" />
        <h2 className="processing-title">Analyzing Your Reviews</h2>
        <p className="processing-status">{statusMessage || "Initializing pipeline…"}</p>

        <div className="progress-bar-container" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
        </div>
        <div className="progress-percent">{progress}% complete</div>
      </div>
    </section>
  );
}
