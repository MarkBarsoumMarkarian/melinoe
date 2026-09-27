from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Modality(StrEnum):
    CLINICAL = "clinical"
    BULK_RNA = "bulk_rna"
    MIRNA = "mirna"
    SINGLE_CELL = "single_cell"
    SPATIAL = "spatial"
    SOMATIC_VARIANT = "somatic_variant"
    COPY_NUMBER = "copy_number"
    PROTEOMICS = "proteomics"
    PATHOLOGY = "pathology"


class DataSensitivity(StrEnum):
    OPEN = "open"
    CONTROLLED = "controlled"
    SENSITIVE = "sensitive"


class SplitRole(StrEnum):
    DISCOVERY = "discovery"
    INTERNAL_VALIDATION = "internal_validation"
    LOCKED_TEST = "locked_test"
    EXTERNAL_VALIDATION = "external_validation"


class ClaimLevel(StrEnum):
    EXPLORATORY = "exploratory"
    INTERNAL_VALIDATION = "internal_validation"
    EXTERNAL_VALIDATION = "external_validation"
    BIOLOGICAL_SUPPORT = "biological_support"
    CLINICAL_UTILITY = "clinical_utility"


class ProjectObjective(BaseModel):
    question: str = Field(min_length=10)
    analysis_type: str
    primary_outcome: str | None = None
    unit_of_analysis: Literal["patient", "specimen", "cell", "region"] = "patient"
    validation_strategy: str
    intended_claim_level: ClaimLevel = ClaimLevel.EXPLORATORY


class Patient(BaseModel):
    id: str = Field(min_length=1)
    diagnosis: str | None = None
    sex: str | None = None
    age_at_diagnosis: float | None = Field(default=None, ge=0, le=130)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Specimen(BaseModel):
    id: str = Field(min_length=1)
    patient_id: str
    tissue_type: str
    disease_status: str | None = None
    collection_timepoint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Assay(BaseModel):
    id: str = Field(min_length=1)
    specimen_id: str
    modality: Modality
    platform: str | None = None
    batch: str | None = None
    data_path: str
    file_sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Endpoint(BaseModel):
    id: str = Field(min_length=1)
    patient_id: str
    endpoint_type: str
    time: float | None = Field(default=None, ge=0)
    event: bool | None = None
    time_unit: Literal["days", "weeks", "months", "years"] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SplitAssignment(BaseModel):
    patient_id: str
    role: SplitRole
    cohort: str | None = None
    rationale: str | None = None


class ProjectSettings(BaseModel):
    allow_platform_mixing: bool = False
    platform_mixing_justification: str | None = None
    minimum_locked_test_patients: int = Field(default=20, ge=1)
    minimum_survival_events: int = Field(default=20, ge=1)


class ProjectManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    project_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    title: str = Field(min_length=3)
    disease_context: str
    description: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data_sensitivity: DataSensitivity = DataSensitivity.OPEN
    objective: ProjectObjective
    patients: list[Patient] = Field(default_factory=list)
    specimens: list[Specimen] = Field(default_factory=list)
    assays: list[Assay] = Field(default_factory=list)
    endpoints: list[Endpoint] = Field(default_factory=list)
    splits: list[SplitAssignment] = Field(default_factory=list)
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_json_file(cls, path: str | Path) -> ProjectManifest:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def patient_map(self) -> dict[str, Patient]:
        return {patient.id: patient for patient in self.patients}

    def specimen_map(self) -> dict[str, Specimen]:
        return {specimen.id: specimen for specimen in self.specimens}

    def patient_for_assay(self, assay: Assay) -> Patient | None:
        specimen = self.specimen_map().get(assay.specimen_id)
        if specimen is None:
            return None
        return self.patient_map().get(specimen.patient_id)
