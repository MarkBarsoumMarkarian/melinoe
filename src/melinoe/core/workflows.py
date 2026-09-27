from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, Field

from melinoe.core.audit import AuditReport, Severity
from melinoe.core.models import Modality, ProjectManifest
from melinoe.core.policy import ProjectPolicy, policy_for


class WorkflowMaturity(StrEnum):
    DESIGN_CONTRACT = "design_contract"
    VALIDATED = "validated"


class WorkflowValidationSummary(BaseModel):
    benchmark_id: str
    evidence_path: str
    independent_cohorts: int = Field(ge=1)
    patients: int = Field(ge=1)
    events: int = Field(ge=1)
    last_validated: str
    status: str = "passed"
    claim_boundary: str


class WorkflowSpec(BaseModel):
    id: str
    version: str = "0.1.0"
    title: str
    summary: str
    required_modalities: set[Modality] = Field(default_factory=set)
    minimum_modalities: int = 1
    required_manifest_objects: set[str] = Field(default_factory=set)
    maturity: WorkflowMaturity = WorkflowMaturity.DESIGN_CONTRACT
    validation: WorkflowValidationSummary | None = None


class WorkflowPlan(BaseModel):
    workflow: WorkflowSpec
    status: str
    manifest_sha256: str
    matched_assay_ids: list[str]
    blocking_finding_codes: list[str]
    unmet_requirements: list[str]
    project_policy: ProjectPolicy
    message: str


WORKFLOW_REGISTRY: tuple[WorkflowSpec, ...] = (
    WorkflowSpec(
        id="bulk-transcriptomics",
        version="1.0.0",
        title="Cohort-native survival synthesis",
        summary=(
            "Censoring-aware cohort-specific Cox models, proportional-hazards checks, "
            "random-effects synthesis, and transportability diagnostics."
        ),
        required_modalities={Modality.BULK_RNA},
        required_manifest_objects={"patients", "specimens", "assays", "endpoints"},
        maturity=WorkflowMaturity.VALIDATED,
        validation=WorkflowValidationSummary(
            benchmark_id="pdac-gprc5a-five-cohort-v2",
            evidence_path="/api/workflows/bulk-transcriptomics/evidence",
            independent_cohorts=5,
            patients=481,
            events=304,
            last_validated="2026-09-27",
            claim_boundary=(
                "Computational reference validation; not clinical validation or therapeutic evidence."
            ),
        ),
    ),
    WorkflowSpec(
        id="single-cell-tumour-atlas",
        title="Single-cell tumour atlas",
        summary="QC, annotation, composition, and cell-state analysis.",
        required_modalities={Modality.SINGLE_CELL},
        required_manifest_objects={"patients", "specimens", "assays"},
    ),
    WorkflowSpec(
        id="somatic-landscape",
        title="Somatic landscape",
        summary="Somatic variants, copy-number events, and driver context.",
        required_modalities={Modality.SOMATIC_VARIANT},
        required_manifest_objects={"patients", "specimens", "assays"},
    ),
    WorkflowSpec(
        id="digital-pathology",
        title="Digital pathology",
        summary="Whole-slide processing and patient-locked model evaluation.",
        required_modalities={Modality.PATHOLOGY},
        required_manifest_objects={"patients", "specimens", "assays", "splits"},
    ),
    WorkflowSpec(
        id="proteomic-response",
        title="Proteomic response",
        summary="Abundance modelling, pathway analysis, and clinical linkage.",
        required_modalities={Modality.PROTEOMICS},
        required_manifest_objects={"patients", "specimens", "assays"},
    ),
    WorkflowSpec(
        id="multimodal-integration",
        title="Multimodal integration",
        summary="Patient-linked late and intermediate evidence fusion.",
        minimum_modalities=2,
        required_manifest_objects={"patients", "specimens", "assays"},
    ),
)


def get_workflow(workflow_id: str) -> WorkflowSpec:
    for workflow in WORKFLOW_REGISTRY:
        if workflow.id == workflow_id:
            return workflow
    raise KeyError(workflow_id)


def plan_workflow(
    manifest: ProjectManifest,
    audit: AuditReport,
    workflow_id: str,
) -> WorkflowPlan:
    workflow = get_workflow(workflow_id)
    project_policy = policy_for(manifest.data_sensitivity)
    available_modalities = {assay.modality for assay in manifest.assays}
    unmet: list[str] = []

    missing_modalities = workflow.required_modalities - available_modalities
    if missing_modalities:
        unmet.append(
            "Missing required modalities: "
            + ", ".join(sorted(modality.value for modality in missing_modalities))
        )
    if len(available_modalities) < workflow.minimum_modalities:
        unmet.append(
            f"Requires at least {workflow.minimum_modalities} modalities; "
            f"project has {len(available_modalities)}"
        )
    for object_name in sorted(workflow.required_manifest_objects):
        if not getattr(manifest, object_name):
            unmet.append(f"Manifest object '{object_name}' is empty")

    blocker_codes = sorted(
        {finding.code for finding in audit.findings if finding.severity == Severity.BLOCKER}
    )
    matched_assays = sorted(
        assay.id
        for assay in manifest.assays
        if not workflow.required_modalities or assay.modality in workflow.required_modalities
    )
    manifest_payload = manifest.model_dump_json(exclude_none=False).encode("utf-8")
    manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()

    if blocker_codes:
        status = "blocked"
        message = "OncoGuard blockers must be resolved before workflow planning can proceed."
    elif unmet:
        status = "ineligible"
        message = "The project does not meet this workflow's declared input contract."
    elif workflow.maturity != WorkflowMaturity.VALIDATED:
        status = "design_only"
        message = "The input contract passes, but this workflow has not yet completed validation."
    else:
        status = "ready"
        message = "The workflow is eligible for version-pinned execution."

    return WorkflowPlan(
        workflow=workflow,
        status=status,
        manifest_sha256=manifest_sha256,
        matched_assay_ids=matched_assays,
        blocking_finding_codes=blocker_codes,
        unmet_requirements=unmet,
        project_policy=project_policy,
        message=message,
    )
