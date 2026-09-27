from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from melinoe import __version__
from melinoe.core.audit import AuditReport
from melinoe.core.models import ProjectManifest
from melinoe.core.policy import ProjectPolicy, policy_for
from melinoe.core.system import SystemProfile, system_profile


class DataObjectState(BaseModel):
    assay_id: str
    declared_path: str
    resolved_path: str | None = None
    exists: bool
    size_bytes: int | None = None
    declared_sha256: str | None = None
    observed_sha256: str | None = None
    checksum_matches: bool | None = None


class ResearchSnapshot(BaseModel):
    format: str = "melinoe-research-state/1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    project_id: str
    melinoe_version: str
    manifest_sha256: str
    audit_sha256: str
    environment_sha256: str
    environment_packages: list[str]
    random_seed: int
    policy: ProjectPolicy
    system: SystemProfile
    data_objects: list[DataObjectState]
    complete_data_verification: bool


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _packages() -> list[str]:
    packages = {
        f"{distribution.metadata['Name']}=={distribution.version}"
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    }
    return sorted(packages, key=str.casefold)


def build_snapshot(
    manifest: ProjectManifest,
    audit: AuditReport,
    *,
    base_path: str | Path | None = None,
    hash_data: bool = False,
    random_seed: int = 20260926,
) -> ResearchSnapshot:
    root = Path(base_path).resolve() if base_path is not None else None
    objects: list[DataObjectState] = []
    for assay in manifest.assays:
        declared = Path(assay.data_path)
        resolved = declared if declared.is_absolute() else root / declared if root else None
        exists = bool(resolved and resolved.is_file())
        observed = _sha256_file(resolved) if exists and hash_data and resolved else None
        objects.append(
            DataObjectState(
                assay_id=assay.id,
                declared_path=assay.data_path,
                resolved_path=str(resolved) if resolved else None,
                exists=exists,
                size_bytes=resolved.stat().st_size if exists and resolved else None,
                declared_sha256=assay.file_sha256,
                observed_sha256=observed,
                checksum_matches=(
                    observed == assay.file_sha256 if observed and assay.file_sha256 else None
                ),
            )
        )
    packages = _packages()
    manifest_payload = manifest.model_dump(mode="json")
    audit_payload = audit.model_dump(mode="json")
    environment = {
        "packages": packages,
        "python": platform.python_version(),
        "melinoe": __version__,
    }
    verification_complete = bool(objects) and all(
        item.exists and item.observed_sha256 and item.checksum_matches is True for item in objects
    )
    return ResearchSnapshot(
        project_id=manifest.project_id,
        melinoe_version=__version__,
        manifest_sha256=hashlib.sha256(_canonical(manifest_payload)).hexdigest(),
        audit_sha256=hashlib.sha256(_canonical(audit_payload)).hexdigest(),
        environment_sha256=hashlib.sha256(_canonical(environment)).hexdigest(),
        environment_packages=packages,
        random_seed=random_seed,
        policy=policy_for(manifest.data_sensitivity),
        system=system_profile(root or "."),
        data_objects=objects,
        complete_data_verification=verification_complete,
    )
