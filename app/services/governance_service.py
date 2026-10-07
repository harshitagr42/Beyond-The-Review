from __future__ import annotations

from app.config import Settings
from app.repositories.base import Repository
from app.schemas.governance import (
    AuditEvent,
    DataQualityBlock,
    DriftBlock,
    GovernanceMetrics,
    ModelsBlock,
    PiiBlock,
    ValidationBlock,
)
from app.services.job_service import JobService
from app.utils.errors import AppError

PII_TAGS = ["[EMAIL_REDACTED]", "[PHONE_REDACTED]", "[PII_REDACTED]"]
VALIDATION_CAVEAT = "Measured on a small synthetic set; indicative only, not real-world accuracy."


class GovernanceService:
    def __init__(self, repo: Repository, jobs: JobService, settings: Settings) -> None:
        self.repo = repo
        self.jobs = jobs
        self.settings = settings

    def metrics(self, job_id: str) -> GovernanceMetrics:
        job_id = self.jobs.require_job_id(job_id)
        job = self.jobs.require_completed(job_id)
        result = self.repo.get_result(job_id)
        if result is None:
            raise AppError(404, "JOB_NOT_FOUND", "Job results were not found.")
        meta = result.get("meta") or {}
        pii = meta.get("pii_breakdown") or {}
        by_type = {
            "email": int(pii.get("email") or 0),
            "phone": int(pii.get("phone") or 0),
            "credit_card": int(pii.get("credit_card") or 0),
            "ssn": int(pii.get("ssn") or 0),
            "ip_address": int(pii.get("ip_address") or 0),
            "person": int(pii.get("person") or 0),
        }
        validation = meta.get("validation") or {}
        drift = meta.get("drift") or {}
        backends = meta.get("backends") or {}
        llm = backends.get("llm_assist") or "off"
        tier2 = backends.get("tier2") or []
        if isinstance(tier2, str):
            tier2 = [tier2]
        audit = [
            AuditEvent(timestamp=e["timestamp"], event=e["event"], details=e.get("details") or {})
            for e in self.repo.list_audit(job_id)
        ]
        return GovernanceMetrics(
            job_id=job_id,
            pii=PiiBlock(
                total_redacted=int(result["summary"].get("pii_redacted_count") or pii.get("total") or 0),
                by_type=by_type,
                tags=PII_TAGS,
                raw_text_stored=False,
            ),
            validation=ValidationBlock(
                display=str(validation.get("display") or result["summary"].get("model_validation_accuracy") or ""),
                overall_accuracy=validation.get("overall_accuracy"),
                sentiment_accuracy=validation.get("sentiment_accuracy"),
                tier1_topic_accuracy=validation.get("tier1_topic_accuracy"),
                sentiment_recall_by_class=validation.get("sentiment_recall_by_class") or {},
                n=validation.get("n"),
                dataset=validation.get("dataset"),
                caveat=VALIDATION_CAVEAT,
            ),
            drift=DriftBlock(
                display=drift.get("display") or result["summary"].get("drift_status"),
                status=drift.get("status"),
                psi=drift.get("psi"),
                centroid_cosine_distance=drift.get("centroid_cosine_distance"),
                baseline_source=drift.get("baseline_source"),
                baseline_size=drift.get("baseline_size"),
            ),
            models=ModelsBlock(
                device=meta.get("device"),
                sentiment_backend=backends.get("sentiment"),
                tier1_backend=backends.get("tier1"),
                tier2_backends=list(tier2),
                embeddings=backends.get("embeddings"),
                llm_assist=str(llm),
                external_data_egress=str(llm) != "off",
            ),
            data_quality=DataQualityBlock(
                rows_received=job.rows_received,
                rows_analyzed=job.rows_analyzed,
                rows_dropped=job.rows_dropped,
                dropped_reasons=job.dropped_reasons or {},
                warnings=list(job.warnings or []) + list(meta.get("warnings") or []),
            ),
            audit_log=audit,
        )
