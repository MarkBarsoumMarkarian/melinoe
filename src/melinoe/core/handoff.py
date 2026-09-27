from __future__ import annotations

import hashlib
import json
import re
import shlex
import stat
import zipfile
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from melinoe.core.audit import AuditReport, Severity
from melinoe.core.models import ProjectManifest
from melinoe.core.policy import NetworkPolicy
from melinoe.core.signing import SignatureEnvelope, sign_payload, verify_payload
from melinoe.core.snapshot import ResearchSnapshot
from melinoe.core.workflow_lock import SignedWorkflowLock, WorkflowLock


class SlurmProfile(BaseModel):
    partition: str | None = None
    account: str | None = None
    network_isolation_command: list[str] | None = None
    extra_directives: list[str] = Field(default_factory=list)

    @field_validator("partition", "account")
    @classmethod
    def validate_slurm_name(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError(
                "Slurm names may contain only letters, numbers, dot, underscore, hyphen"
            )
        return value

    @field_validator("extra_directives")
    @classmethod
    def validate_directives(cls, values: list[str]) -> list[str]:
        protected = {"--export", "--chdir", "--output", "--error", "--job-name"}
        for value in values:
            if "\n" in value or "\r" in value or not value.startswith("--"):
                raise ValueError("extra Slurm directives must be single-line long options")
            option = value.split("=", 1)[0]
            if option in protected:
                raise ValueError(f"Melinoë controls the {option} directive")
        return values


class HandoffVerification(BaseModel):
    valid: bool
    project_id: str | None = None
    workflow_id: str | None = None
    signer_key_id: str | None = None
    errors: list[str] = Field(default_factory=list)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, default=str).encode("utf-8") + b"\n"


def _slurm_script(lock: SignedWorkflowLock, profile: SlurmProfile) -> str:
    workflow = lock.lock
    directives = [
        f"#SBATCH --job-name=melinoe-{workflow.workflow_id[:32]}",
        f"#SBATCH --cpus-per-task={workflow.resources.cpus}",
        f"#SBATCH --mem={workflow.resources.memory_gib}G",
        f"#SBATCH --time={workflow.resources.walltime}",
        "#SBATCH --export=NIL",
        "#SBATCH --output=logs/%x-%j.out",
        "#SBATCH --error=logs/%x-%j.err",
    ]
    if workflow.resources.gpus:
        directives.append(f"#SBATCH --gpus={workflow.resources.gpus}")
    if profile.partition:
        directives.append(f"#SBATCH --partition={profile.partition}")
    if profile.account:
        directives.append(f"#SBATCH --account={profile.account}")
    directives.extend(f"#SBATCH {item}" for item in profile.extra_directives)
    prefix = profile.network_isolation_command or []
    command = [
        *prefix,
        "apptainer",
        "exec",
        "--containall",
        "--cleanenv",
        "--no-home",
        "--no-privs",
    ]
    if workflow.resources.gpus:
        command.append("--nv")
    rendered_command = " ".join(shlex.quote(item) for item in command)
    rendered_command += (
        ' --bind "${SLURM_SUBMIT_DIR}:/workspace" --cwd /workspace "${MELINOE_SIF}" '
        + " ".join(shlex.quote(item) for item in workflow.command)
    )
    expected = workflow.container.sif_sha256
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            *directives,
            "",
            "set -euo pipefail",
            'export PATH="/usr/local/bin:/usr/bin:/bin"',
            'mkdir -p "$SLURM_SUBMIT_DIR/logs" "$SLURM_SUBMIT_DIR/outputs"',
            ': "${MELINOE_SIF:?Set MELINOE_SIF to the staged, immutable SIF image}"',
            'test -f "$MELINOE_SIF"',
            'command -v apptainer >/dev/null || { echo "Apptainer is required" >&2; exit 127; }',
            f'EXPECTED_SIF_SHA256="{expected}"',
            'OBSERVED_SIF_SHA256="$(sha256sum "$MELINOE_SIF" | awk \'{print $1}\')"',
            'test "$OBSERVED_SIF_SHA256" = "$EXPECTED_SIF_SHA256" || {',
            '  echo "Container checksum mismatch; refusing execution" >&2',
            "  exit 42",
            "}",
            rendered_command,
            "",
        ]
    )


def _write_executable(archive: zipfile.ZipFile, name: str, content: str) -> None:
    info = zipfile.ZipInfo(name)
    info.external_attr = 0o100755 << 16
    archive.writestr(info, content.encode("utf-8"))


def build_hpc_handoff(
    manifest: ProjectManifest,
    audit: AuditReport,
    snapshot: ResearchSnapshot,
    signed_lock: SignedWorkflowLock,
    output: str | Path,
    profile: SlurmProfile,
    private_key: str | Path,
    passphrase: str,
) -> Path:
    blockers = [finding.code for finding in audit.findings if finding.severity == Severity.BLOCKER]
    if blockers:
        raise ValueError("OncoGuard blockers prevent handoff: " + ", ".join(sorted(blockers)))
    if not signed_lock.verify():
        raise ValueError("workflow-lock signature verification failed")
    if not signed_lock.lock.executable:
        raise ValueError("workflow lock is not backed by declared validation evidence")
    if not signed_lock.lock.container.sif_sha256:
        raise ValueError("HPC execution requires a pinned SIF file checksum")
    available = {assay.modality for assay in manifest.assays}
    missing = signed_lock.lock.required_modalities - available
    if missing:
        raise ValueError("project is missing required modalities: " + ", ".join(sorted(missing)))
    if signed_lock.lock.network == NetworkPolicy.DENY and not profile.network_isolation_command:
        raise ValueError("network-denied workflows require a cluster isolation command")

    contents = {
        "project.json": _json_bytes(manifest.model_dump(mode="json")),
        "audit.json": _json_bytes(audit.model_dump(mode="json")),
        "research-state.json": _json_bytes(snapshot.model_dump(mode="json")),
        "workflow-lock.json": _json_bytes(signed_lock.lock.model_dump(mode="json")),
        "workflow-signature.json": _json_bytes(signed_lock.signature.model_dump(mode="json")),
        "slurm-profile.json": _json_bytes(profile.model_dump(mode="json")),
    }
    crate = {
        "@context": "https://w3id.org/ro/crate/1.3/context",
        "@graph": [
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.3"},
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": f"Melinoë HPC handoff: {manifest.title}",
                "description": "Signed, validity-gated, digest-pinned Slurm execution handoff.",
                "hasPart": [{"@id": name} for name in contents] + [{"@id": "submit.slurm"}],
            },
            *[{"@id": name, "@type": "File", "name": name} for name in [*contents, "submit.slurm"]],
        ],
    }
    contents["ro-crate-metadata.json"] = _json_bytes(crate)
    slurm = _slurm_script(signed_lock, profile)
    index = {
        "format": "melinoe-hpc-handoff/1.0",
        "project_id": manifest.project_id,
        "workflow_id": signed_lock.lock.workflow_id,
        "files": {
            **{name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
            "submit.slurm": hashlib.sha256(slurm.encode()).hexdigest(),
        },
    }
    handoff_signature = sign_payload(index, private_key, passphrase)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
        _write_executable(archive, "submit.slurm", slurm)
        archive.writestr("handoff-index.json", _json_bytes(index))
        archive.writestr(
            "handoff-signature.json",
            _json_bytes(handoff_signature.model_dump(mode="json")),
        )
    return output_path


def verify_hpc_handoff(path: str | Path) -> HandoffVerification:
    errors: list[str] = []
    project_id = workflow_id = signer_key_id = None
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                errors.append("archive contains duplicate member names")
            for info in infos:
                member = Path(info.filename)
                if member.is_absolute() or ".." in member.parts:
                    errors.append(f"unsafe archive path: {info.filename}")
                if stat.S_ISLNK(info.external_attr >> 16):
                    errors.append(f"archive contains a symlink: {info.filename}")
            index = json.loads(archive.read("handoff-index.json"))
            signature = SignatureEnvelope.model_validate_json(
                archive.read("handoff-signature.json")
            )
            project_id = index.get("project_id")
            workflow_id = index.get("workflow_id")
            signer_key_id = signature.key_id
            signed = verify_payload(index, signature)
            if not signed.valid:
                errors.append(signed.error or "handoff signature verification failed")
            declared = set(index.get("files", {}))
            expected_members = declared | {"handoff-index.json", "handoff-signature.json"}
            if set(names) != expected_members:
                errors.append("archive members do not match the signed handoff index")
            for name, expected in index.get("files", {}).items():
                observed = hashlib.sha256(archive.read(name)).hexdigest()
                if observed != expected:
                    errors.append(f"checksum mismatch: {name}")
            lock = WorkflowLock.model_validate_json(archive.read("workflow-lock.json"))
            workflow_signature = SignatureEnvelope.model_validate_json(
                archive.read("workflow-signature.json")
            )
            if not SignedWorkflowLock(lock=lock, signature=workflow_signature).verify():
                errors.append("embedded workflow-lock signature is invalid")
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        errors.append(str(error))
    return HandoffVerification(
        valid=not errors,
        project_id=project_id,
        workflow_id=workflow_id,
        signer_key_id=signer_key_id,
        errors=errors,
    )
