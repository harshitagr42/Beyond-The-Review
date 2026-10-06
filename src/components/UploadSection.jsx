import { useRef, useState, useCallback } from "react";
import { Upload, Download, FileSpreadsheet } from "lucide-react";
import { sampleCSVContent } from "../api/mock/mockData";

export default function UploadSection({ onFileSelected }) {
  const fileInputRef = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);

  /* ── Drag & Drop handlers ─────────────────────────────────── */
  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) validateAndEmit(file);
    },
    [onFileSelected]
  );

  /* ── File picker ──────────────────────────────────────────── */
  const handleInputChange = useCallback(
    (e) => {
      const file = e.target.files?.[0];
      if (file) validateAndEmit(file);
    },
    [onFileSelected]
  );

  const validateAndEmit = (file) => {
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["csv", "xlsx"].includes(ext)) {
      alert("Invalid file format. Only .csv and .xlsx files are supported.");
      return;
    }
    if (file.size > 100 * 1024 * 1024) {
      alert("File size exceeds 100 MB limit.");
      return;
    }
    onFileSelected(file);
  };

  /* ── Sample CSV download ──────────────────────────────────── */
  const downloadSample = () => {
    const blob = new Blob([sampleCSVContent], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "sample_reviews.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <section className="upload-section" id="upload-section">
      <div className="upload-hero-text">
        <h1>Analyze Customer Feedback</h1>
        <p>
          Upload your review dataset and get instant sentiment analysis,
          complaint themes, PII redaction, and actionable insights.
        </p>
      </div>

      {/* Dropzone */}
      <div
        className={`upload-dropzone${isDragOver ? " drag-over" : ""}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Upload review file"
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click(); }}
      >
        <div className="dropzone-icon">
          <Upload size={28} />
        </div>
        <div className="dropzone-text">
          Drag &amp; drop your review file here
        </div>
        <div className="dropzone-subtext">
          or <span>browse from your computer</span>
        </div>
        <div className="dropzone-formats">
          <span className="format-badge">.csv</span>
          <span className="format-badge">.xlsx</span>
          <span className="format-badge">up to 100 mb</span>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          className="upload-file-input"
          accept=".csv,.xlsx"
          onChange={handleInputChange}
          aria-hidden="true"
        />
      </div>

      {/* Actions */}
      <div className="upload-actions">
        <button className="sample-download-btn" onClick={downloadSample} id="download-sample-btn">
          <Download size={14} />
          Download Sample CSV
        </button>
        <button
          className="sample-download-btn"
          onClick={() => onFileSelected(null)}
          id="demo-mode-btn"
          style={{ background: "var(--color-accent-deep)", color: "white", borderColor: "var(--color-accent-deep)" }}
        >
          <FileSpreadsheet size={14} />
          Try Demo Mode
        </button>
      </div>
    </section>
  );
}
