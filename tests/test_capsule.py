import hashlib
import json
import zipfile
from io import BytesIO

from melinoe.core.capsule import build_capsule
from melinoe.core.models import ProjectManifest
from melinoe.rules.engine import OncoGuard


def test_capsule_contains_manifest_audit_provenance_and_summary(
    demo_manifest: ProjectManifest,
) -> None:
    report = OncoGuard().audit(demo_manifest)
    payload = build_capsule(demo_manifest, report)

    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "audit.json",
            "research-state.json",
            "provenance.json",
            "SUMMARY.md",
            "capsule-index.json",
            "ro-crate-metadata.json",
        }
        manifest_bytes = archive.read("manifest.json")
        audit_bytes = archive.read("audit.json")
        provenance = json.loads(archive.read("provenance.json"))
        state = json.loads(archive.read("research-state.json"))
        index = json.loads(archive.read("capsule-index.json"))
        ro_crate = json.loads(archive.read("ro-crate-metadata.json"))
        summary = archive.read("SUMMARY.md").decode("utf-8")

    assert provenance["source_data_included"] is False
    assert provenance["manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    assert provenance["audit_sha256"] == hashlib.sha256(audit_bytes).hexdigest()
    assert state["format"] == "melinoe-research-state/1.0"
    assert index["files"]["manifest.json"] == hashlib.sha256(manifest_bytes).hexdigest()
    assert ro_crate["@context"] == "https://w3id.org/ro/crate/1.3/context"
    assert ro_crate["@graph"][0]["@id"] == "ro-crate-metadata.json"
    assert "Audit status: **blocked**" in summary
