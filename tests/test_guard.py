from melinoe.core.models import (
    Assay,
    Endpoint,
    Patient,
    ProjectManifest,
    ProjectObjective,
    Specimen,
    SplitAssignment,
)
from melinoe.rules.engine import OncoGuard


def test_demo_triggers_cross_domain_safety_rules(demo_manifest: ProjectManifest) -> None:
    report = OncoGuard().audit(demo_manifest)
    codes = {finding.code for finding in report.findings}

    assert report.summary.status == "blocked"
    assert report.summary.score == 0
    assert {
        "OG-002",
        "OG-003",
        "OG-004",
        "PR-001",
        "AS-001",
        "AS-002",
        "AS-003",
        "EP-001",
        "EP-002",
        "EV-002",
        "CL-001",
        "PV-001",
        "IN-002",
    } <= codes


def test_batch_outcome_finding_names_the_confounded_batches(
    demo_manifest: ProjectManifest,
) -> None:
    report = OncoGuard().audit(demo_manifest)
    finding = next(item for item in report.findings if item.code == "AS-003")
    assert finding.severity.value == "blocker"
    assert "RUN_A" in finding.evidence[0]
    assert "RUN_B" in finding.evidence[0]


def test_removing_direct_identifier_clears_privacy_blocker(
    demo_manifest: ProjectManifest,
) -> None:
    demo_manifest.patients[2].metadata.pop("email")
    report = OncoGuard().audit(demo_manifest)
    assert "PR-001" not in {finding.code for finding in report.findings}


def test_well_formed_externally_validated_project_is_not_blocked() -> None:
    patients = [
        Patient(id=f"P{index:03d}", diagnosis="PDAC", metadata={"response": index % 2})
        for index in range(40)
    ]
    specimens = [
        Specimen(
            id=f"S{index:03d}",
            patient_id=patient.id,
            tissue_type="primary tumour",
            disease_status="tumour",
        )
        for index, patient in enumerate(patients)
    ]
    assays = [
        Assay(
            id=f"A{index:03d}",
            specimen_id=specimen.id,
            modality="bulk_rna",
            platform="Illumina NovaSeq",
            batch="balanced_batch",
            data_path=f"data/P{index:03d}.tsv",
            file_sha256=f"{index:064x}",
        )
        for index, specimen in enumerate(specimens)
    ]
    endpoints = [
        Endpoint(
            id=f"OS{index:03d}",
            patient_id=patient.id,
            endpoint_type="overall_survival",
            time=12 + index,
            event=True,
            time_unit="months",
        )
        for index, patient in enumerate(patients)
    ]
    splits = [
        SplitAssignment(
            patient_id=patient.id,
            role=(
                "discovery"
                if index < 10
                else "locked_test"
                if index < 30
                else "external_validation"
            ),
            cohort="reference",
        )
        for index, patient in enumerate(patients)
    ]
    manifest = ProjectManifest(
        project_id="well_formed_reference",
        title="Well-formed reference project",
        disease_context="Pancreatic ductal adenocarcinoma",
        objective=ProjectObjective(
            question="Can a locked molecular model reproduce in an independent PDAC cohort?",
            analysis_type="external validation",
            primary_outcome="response",
            validation_strategy="discovery, locked test, and external validation",
            intended_claim_level="external_validation",
        ),
        patients=patients,
        specimens=specimens,
        assays=assays,
        endpoints=endpoints,
        splits=splits,
    )

    report = OncoGuard().audit(manifest)

    assert report.summary.score == 100
    assert report.summary.status == "ready_with_caveats"
    assert {finding.code for finding in report.findings} == {"IN-002"}
