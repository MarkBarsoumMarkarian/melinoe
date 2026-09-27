from __future__ import annotations

import hashlib
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from melinoe.core.models import Modality
from melinoe.core.policy import NetworkPolicy
from melinoe.core.signing import (
    SignatureEnvelope,
    canonical_json,
    sign_payload,
    verify_payload,
)

OCI_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")


class ContainerPin(BaseModel):
    reference: str
    oci_digest: str
    sif_sha256: str | None = None
    sbom_sha256: str | None = None

    @field_validator("oci_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not OCI_DIGEST.fullmatch(value):
            raise ValueError("OCI images must be pinned by a lowercase sha256 digest")
        return value

    @field_validator("sif_sha256", "sbom_sha256")
    @classmethod
    def validate_optional_hash(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[a-f0-9]{64}", value):
            raise ValueError("file checksums must be lowercase SHA-256 hex")
        return value


class ResourceContract(BaseModel):
    cpus: int = Field(default=4, ge=1, le=1024)
    memory_gib: int = Field(default=16, ge=1)
    walltime: str = Field(default="04:00:00", pattern=r"^\d{2,3}:\d{2}:\d{2}$")
    gpus: int = Field(default=0, ge=0)


class WorkflowLock(BaseModel):
    format: str = "melinoe-workflow-lock/1.0"
    workflow_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    workflow_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$")
    maturity: str
    validation_evidence: list[str] = Field(default_factory=list)
    required_modalities: set[Modality] = Field(default_factory=set)
    container: ContainerPin
    command: list[str] = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    resources: ResourceContract = Field(default_factory=ResourceContract)
    network: NetworkPolicy = NetworkPolicy.DENY
    random_seed: int = 20260926

    @property
    def executable(self) -> bool:
        return self.maturity == "validated" and bool(self.validation_evidence)

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.model_dump(mode="json"))).hexdigest()


class SignedWorkflowLock(BaseModel):
    lock: WorkflowLock
    signature: SignatureEnvelope

    def verify(self) -> bool:
        return verify_payload(self.lock.model_dump(mode="json"), self.signature).valid


def sign_workflow_lock(
    lock: WorkflowLock,
    private_path: str,
    passphrase: str,
) -> SignedWorkflowLock:
    if not lock.executable:
        raise ValueError("only validated workflows with evidence can be signed for execution")
    signature = sign_payload(lock.model_dump(mode="json"), private_path, passphrase)
    return SignedWorkflowLock(lock=lock, signature=signature)
