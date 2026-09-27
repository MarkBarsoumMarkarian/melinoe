from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from melinoe.core.models import ProjectManifest


class Severity(StrEnum):
    BLOCKER = "blocker"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Finding(BaseModel):
    code: str
    title: str
    severity: Severity
    message: str
    evidence: list[str] = Field(default_factory=list)
    remediation: str
    affected_entities: list[str] = Field(default_factory=list)


class AuditSummary(BaseModel):
    score: int
    status: str
    finding_counts: dict[str, int]
    patient_count: int
    specimen_count: int
    assay_count: int
    modality_count: int


class AuditReport(BaseModel):
    project_id: str
    engine_version: str = "0.1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    summary: AuditSummary
    findings: list[Finding]
    rule_codes_executed: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


def summarize(manifest: ProjectManifest, findings: list[Finding]) -> AuditSummary:
    weights = {
        Severity.BLOCKER: 25,
        Severity.HIGH: 12,
        Severity.MEDIUM: 5,
        Severity.LOW: 2,
        Severity.INFO: 0,
    }
    score = max(0, 100 - sum(weights[finding.severity] for finding in findings))
    counts = Counter(finding.severity.value for finding in findings)
    status = "blocked" if counts[Severity.BLOCKER.value] else "review_required"
    if not any(counts[level.value] for level in (Severity.HIGH, Severity.MEDIUM)):
        status = "ready_with_caveats" if findings else "ready"
    return AuditSummary(
        score=score,
        status=status,
        finding_counts={level.value: counts[level.value] for level in Severity},
        patient_count=len(manifest.patients),
        specimen_count=len(manifest.specimens),
        assay_count=len(manifest.assays),
        modality_count=len({assay.modality for assay in manifest.assays}),
    )
