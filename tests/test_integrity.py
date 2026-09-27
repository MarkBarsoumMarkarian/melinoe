import json
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from melinoe.core.audit import AuditReport, AuditSummary
from melinoe.core.checkpoints import (
    create_checkpoint,
    list_checkpoints,
    restore_checkpoint,
    verify_checkpoint,
)
from melinoe.core.handoff import SlurmProfile, build_hpc_handoff, verify_hpc_handoff
from melinoe.core.knowledge import (
    KnowledgeManifest,
    KnowledgeSource,
    build_knowledge_pack,
    install_knowledge_pack,
    list_knowledge_packs,
    verify_knowledge_pack,
)
from melinoe.core.models import Assay, Patient, ProjectManifest, ProjectObjective, Specimen
from melinoe.core.signing import generate_signing_key, sign_payload, verify_payload
from melinoe.core.snapshot import build_snapshot
from melinoe.core.workflow_lock import (
    ContainerPin,
    SignedWorkflowLock,
    WorkflowLock,
    sign_workflow_lock,
)


def _project() -> ProjectManifest:
    return ProjectManifest(
        project_id="integrity_reference",
        title="Integrity reference project",
        disease_context="Pancreatic ductal adenocarcinoma",
        data_sensitivity="controlled",
        objective=ProjectObjective(
            question="Can this frozen workflow reproduce a declared molecular association?",
            analysis_type="technical replication",
            validation_strategy="independent locked execution",
        ),
        patients=[Patient(id="P001", diagnosis="PDAC")],
        specimens=[Specimen(id="S001", patient_id="P001", tissue_type="tumour")],
        assays=[
            Assay(
                id="A001",
                specimen_id="S001",
                modality="bulk_rna",
                platform="test",
                batch="B1",
                data_path="data/expression.tsv",
                file_sha256="a" * 64,
            )
        ],
    )


def _audit(project: ProjectManifest) -> AuditReport:
    return AuditReport(
        project_id=project.project_id,
        summary=AuditSummary(
            score=100,
            status="ready",
            finding_counts={
                "blocker": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "info": 0,
            },
            patient_count=1,
            specimen_count=1,
            assay_count=1,
            modality_count=1,
        ),
        findings=[],
        rule_codes_executed=[],
    )


def _keys(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "signing.pem"
    public = tmp_path / "signing.pub"
    generate_signing_key(private, public, "correct horse battery staple")
    return private, public


def _workflow(private: Path) -> SignedWorkflowLock:
    lock = WorkflowLock(
        workflow_id="bulk-reference",
        workflow_version="1.0.0",
        maturity="validated",
        validation_evidence=["gold-study:bulk-reference-v1"],
        required_modalities={"bulk_rna"},
        container=ContainerPin(
            reference="registry.example.org/melinoe/bulk-reference",
            oci_digest="sha256:" + "b" * 64,
            sif_sha256="c" * 64,
            sbom_sha256="d" * 64,
        ),
        command=["python", "/workflow/run.py", "--manifest", "/workspace/project.json"],
        network="deny",
    )
    return sign_workflow_lock(lock, str(private), "correct horse battery staple")


def test_ed25519_signatures_detect_payload_changes(tmp_path: Path) -> None:
    private, _ = _keys(tmp_path)
    assert oct(os.stat(private).st_mode & 0o777) == "0o600"
    payload = {"workflow": "bulk-reference", "version": 1}
    signature = sign_payload(payload, private, "correct horse battery staple")

    assert verify_payload(payload, signature).valid is True
    assert verify_payload({**payload, "version": 2}, signature).valid is False


def test_workflow_lock_requires_digest_and_validation_evidence(tmp_path: Path) -> None:
    private, _ = _keys(tmp_path)
    signed = _workflow(private)
    assert signed.verify() is True
    assert signed.lock.executable is True

    tampered = signed.model_copy(deep=True)
    tampered.lock.workflow_version = "9.9.9"
    assert tampered.verify() is False

    with pytest.raises(ValidationError):
        ContainerPin(reference="example/latest", oci_digest="latest")


def test_signed_offline_knowledge_pack_lifecycle(tmp_path: Path) -> None:
    private, _ = _keys(tmp_path)
    source = tmp_path / "knowledge"
    source.mkdir()
    (source / "genes.json").write_text('{"TP53": "tumour suppressor"}\n', encoding="utf-8")
    metadata = KnowledgeManifest(
        pack_id="cancer_core",
        version="2026.09",
        title="Cancer core test knowledge",
        description="Small deterministic fixture.",
        sources=[
            KnowledgeSource(
                name="fixture",
                version="1",
                url="https://example.org/fixture",
                license="CC0-1.0",
                retrieved_at=datetime.now(UTC),
            )
        ],
    )
    package = build_knowledge_pack(
        source,
        metadata,
        tmp_path / "cancer-core.mknowledge",
        private,
        "correct horse battery staple",
    )

    verification = verify_knowledge_pack(package)
    assert verification.valid is True
    assert verification.file_count == 1
    installed = install_knowledge_pack(package, tmp_path / "registry")
    assert installed.is_file()
    assert list_knowledge_packs(tmp_path / "registry")[0].valid is True

    tampered = tmp_path / "tampered.mknowledge"
    with zipfile.ZipFile(package) as source_archive, zipfile.ZipFile(tampered, "w") as target:
        for info in source_archive.infolist():
            content = source_archive.read(info.filename)
            target.writestr(info, b"tampered" if info.filename == "data/genes.json" else content)
    assert verify_knowledge_pack(tampered).valid is False


def test_checkpoint_restore_preserves_current_manifest(tmp_path: Path) -> None:
    project = _project()
    audit = _audit(project)
    state = build_snapshot(project, audit, base_path=tmp_path)
    checkpoint = create_checkpoint(tmp_path, project, audit, state)
    assert verify_checkpoint(checkpoint).valid is True
    assert len(list_checkpoints(tmp_path)) == 1

    manifest_path = tmp_path / "project.json"
    changed = project.model_copy(update={"title": "Changed title"})
    manifest_path.write_text(changed.model_dump_json(indent=2) + "\n", encoding="utf-8")
    backup = restore_checkpoint(tmp_path, checkpoint.name, manifest_path)

    assert backup is not None and backup.is_file()
    assert ProjectManifest.from_json_file(manifest_path).title == project.title
    assert ProjectManifest.from_json_file(backup).title == "Changed title"


def test_hpc_handoff_is_signed_gated_and_digest_pinned(tmp_path: Path) -> None:
    private, _ = _keys(tmp_path)
    signed = _workflow(private)
    project = _project()
    audit = _audit(project)
    state = build_snapshot(project, audit, base_path=tmp_path)
    output = tmp_path / "handoff.zip"

    build_hpc_handoff(
        project,
        audit,
        state,
        signed,
        output,
        SlurmProfile(network_isolation_command=["unshare", "--net", "--"]),
        private,
        "correct horse battery staple",
    )

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        script = archive.read("submit.slurm").decode("utf-8")
        lock = json.loads(archive.read("workflow-lock.json"))
        crate = json.loads(archive.read("ro-crate-metadata.json"))
    assert {
        "handoff-index.json",
        "handoff-signature.json",
        "workflow-signature.json",
        "submit.slurm",
    } <= names
    assert "#SBATCH --export=NIL" in script
    assert "EXPECTED_SIF_SHA256" in script
    assert "unshare --net -- apptainer exec" in script
    assert lock["container"]["oci_digest"] == "sha256:" + "b" * 64
    assert crate["@context"] == "https://w3id.org/ro/crate/1.3/context"
    assert verify_hpc_handoff(output).valid is True

    tampered = tmp_path / "tampered-handoff.zip"
    with zipfile.ZipFile(output) as source_archive, zipfile.ZipFile(tampered, "w") as target:
        for info in source_archive.infolist():
            content = source_archive.read(info.filename)
            target.writestr(info, b"{}\n" if info.filename == "project.json" else content)
    assert verify_hpc_handoff(tampered).valid is False

    with pytest.raises(ValueError, match="cluster isolation command"):
        build_hpc_handoff(
            project,
            audit,
            state,
            signed,
            output,
            SlurmProfile(),
            private,
            "correct horse battery staple",
        )
