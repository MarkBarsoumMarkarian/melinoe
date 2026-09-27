from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from melinoe.core.models import DataSensitivity


class NetworkPolicy(StrEnum):
    DENY = "deny"
    KNOWLEDGE_ONLY = "knowledge_only"
    ALLOW = "allow"


class ExportPolicy(StrEnum):
    CAPSULE_ONLY = "capsule_only"
    DEIDENTIFIED_ONLY = "deidentified_only"
    ALLOW = "allow"


class ProjectPolicy(BaseModel):
    sensitivity: DataSensitivity
    encryption_required: bool
    network: NetworkPolicy
    export: ExportPolicy
    source_data_in_capsules: bool = False
    direct_identifiers_allowed: bool = False
    locked_test_labels_hidden_during_training: bool = True
    rationale: list[str]


def policy_for(sensitivity: DataSensitivity | str) -> ProjectPolicy:
    level = DataSensitivity(sensitivity)
    if level == DataSensitivity.SENSITIVE:
        return ProjectPolicy(
            sensitivity=level,
            encryption_required=True,
            network=NetworkPolicy.DENY,
            export=ExportPolicy.CAPSULE_ONLY,
            rationale=[
                "Sensitive project data must remain in an encrypted Project Vault.",
                "Workflow processes receive no network namespace.",
                "Only metadata-only Research Capsules may leave the project boundary.",
            ],
        )
    if level == DataSensitivity.CONTROLLED:
        return ProjectPolicy(
            sensitivity=level,
            encryption_required=True,
            network=NetworkPolicy.KNOWLEDGE_ONLY,
            export=ExportPolicy.DEIDENTIFIED_ONLY,
            rationale=[
                "Controlled project data must remain in an encrypted Project Vault.",
                "Network access is denied during analysis; curated knowledge updates are separate.",
                "Exports must pass identifier checks and exclude source data.",
            ],
        )
    return ProjectPolicy(
        sensitivity=level,
        encryption_required=False,
        network=NetworkPolicy.ALLOW,
        export=ExportPolicy.ALLOW,
        rationale=[
            "Open data may use the network when a workflow explicitly declares it.",
            "Research Capsules still omit source data by default.",
        ],
    )
