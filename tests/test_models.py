from melinoe.core.models import Modality, ProjectManifest


def test_demo_manifest_loads(demo_manifest: ProjectManifest) -> None:
    assert demo_manifest.project_id == "melinoe_multimodal_demo"
    assert len(demo_manifest.patients) == 8
    assert len(demo_manifest.specimens) == 9
    assert len(demo_manifest.assays) == 12
    assert {assay.modality for assay in demo_manifest.assays} >= {
        Modality.BULK_RNA,
        Modality.PATHOLOGY,
        Modality.PROTEOMICS,
        Modality.SOMATIC_VARIANT,
        Modality.SPATIAL,
    }


def test_assay_resolves_through_specimen_to_patient(demo_manifest: ProjectManifest) -> None:
    assay = next(assay for assay in demo_manifest.assays if assay.id == "RNA001")
    patient = demo_manifest.patient_for_assay(assay)
    assert patient is not None
    assert patient.id == "P001"
