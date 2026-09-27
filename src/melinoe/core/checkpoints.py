from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from melinoe.core.audit import AuditReport
from melinoe.core.ledger import AuditLedger
from melinoe.core.models import ProjectManifest
from melinoe.core.snapshot import ResearchSnapshot


class CheckpointRecord(BaseModel):
    format: str = "melinoe-checkpoint/1.0"
    checkpoint_id: str
    project_id: str
    created_at: datetime
    manifest_sha256: str
    files: dict[str, str]
    includes_source_data: bool = False


class CheckpointVerification(BaseModel):
    valid: bool
    checkpoint_id: str | None = None
    project_id: str | None = None
    errors: list[str] = Field(default_factory=list)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, default=str).encode("utf-8") + b"\n"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_checkpoint(
    project_root: str | Path,
    manifest: ProjectManifest,
    audit: AuditReport,
    snapshot: ResearchSnapshot,
) -> Path:
    root = Path(project_root).resolve()
    checkpoint_root = root / ".melinoe" / "checkpoints"
    checkpoint_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = datetime.now(UTC)
    manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))
    audit_bytes = _json_bytes(audit.model_dump(mode="json"))
    snapshot_bytes = _json_bytes(snapshot.model_dump(mode="json"))
    checkpoint_id = f"{now.strftime('%Y%m%dT%H%M%S%fZ')}-{_sha256(manifest_bytes)[:12]}"
    destination = checkpoint_root / checkpoint_id
    temporary = Path(tempfile.mkdtemp(prefix=".checkpoint-", dir=checkpoint_root))
    try:
        contents = {
            "manifest.json": manifest_bytes,
            "audit.json": audit_bytes,
            "research-state.json": snapshot_bytes,
        }
        for name, data in contents.items():
            (temporary / name).write_bytes(data)
        record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            project_id=manifest.project_id,
            created_at=now,
            manifest_sha256=_sha256(manifest_bytes),
            files={name: _sha256(data) for name, data in contents.items()},
        )
        (temporary / "checkpoint.json").write_bytes(_json_bytes(record.model_dump(mode="json")))
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    AuditLedger(root / ".melinoe" / "ledger.jsonl").append(
        "checkpoint.created",
        details={"checkpoint_id": checkpoint_id, "manifest_sha256": record.manifest_sha256},
    )
    return destination


def verify_checkpoint(path: str | Path) -> CheckpointVerification:
    checkpoint = Path(path)
    errors: list[str] = []
    checkpoint_id = project_id = None
    try:
        record = CheckpointRecord.model_validate_json(
            (checkpoint / "checkpoint.json").read_text(encoding="utf-8")
        )
        checkpoint_id, project_id = record.checkpoint_id, record.project_id
        if checkpoint.name != record.checkpoint_id:
            errors.append("checkpoint directory name does not match its record")
        for name, expected in record.files.items():
            target = checkpoint / name
            if not target.is_file():
                errors.append(f"missing checkpoint file: {name}")
            elif _sha256(target.read_bytes()) != expected:
                errors.append(f"checksum mismatch: {name}")
        manifest = ProjectManifest.model_validate_json(
            (checkpoint / "manifest.json").read_text(encoding="utf-8")
        )
        if manifest.project_id != record.project_id:
            errors.append("manifest project ID does not match checkpoint record")
    except (OSError, ValueError) as error:
        errors.append(str(error))
    return CheckpointVerification(
        valid=not errors,
        checkpoint_id=checkpoint_id,
        project_id=project_id,
        errors=errors,
    )


def list_checkpoints(project_root: str | Path) -> list[CheckpointRecord]:
    root = Path(project_root).resolve() / ".melinoe" / "checkpoints"
    if not root.exists():
        return []
    records: list[CheckpointRecord] = []
    for path in sorted(root.iterdir(), reverse=True):
        if path.is_dir() and not path.name.startswith("."):
            verification = verify_checkpoint(path)
            if verification.valid:
                records.append(
                    CheckpointRecord.model_validate_json(
                        (path / "checkpoint.json").read_text(encoding="utf-8")
                    )
                )
    return records


def restore_checkpoint(
    project_root: str | Path,
    checkpoint_id: str,
    destination_manifest: str | Path,
) -> Path | None:
    root = Path(project_root).resolve()
    checkpoint = root / ".melinoe" / "checkpoints" / checkpoint_id
    verification = verify_checkpoint(checkpoint)
    if not verification.valid:
        raise ValueError("checkpoint verification failed: " + "; ".join(verification.errors))
    destination = Path(destination_manifest).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if destination.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = destination.with_name(f"{destination.stem}.before-{stamp}{destination.suffix}")
        shutil.copy2(destination, backup)
    descriptor, temporary = tempfile.mkstemp(prefix=".restore-", dir=destination.parent)
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        shutil.copyfile(checkpoint / "manifest.json", temporary_path)
        ProjectManifest.from_json_file(temporary_path)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    AuditLedger(root / ".melinoe" / "ledger.jsonl").append(
        "checkpoint.restored",
        details={
            "checkpoint_id": checkpoint_id,
            "destination": str(destination),
            "backup": str(backup) if backup else None,
        },
    )
    return backup
