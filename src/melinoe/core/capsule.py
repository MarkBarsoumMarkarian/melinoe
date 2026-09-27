from __future__ import annotations

import hashlib
import io
import json
import platform
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from melinoe import __version__
from melinoe.core.audit import AuditReport
from melinoe.core.models import ProjectManifest
from melinoe.core.snapshot import ResearchSnapshot, build_snapshot


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, default=str).encode("utf-8") + b"\n"


def _summary_markdown(manifest: ProjectManifest, audit: AuditReport) -> str:
    counts = audit.summary.finding_counts
    lines = [
        f"# Research Capsule: {manifest.title}",
        "",
        f"- Project: `{manifest.project_id}`",
        f"- Disease context: {manifest.disease_context}",
        f"- Audit status: **{audit.summary.status}**",
        f"- Readiness score: **{audit.summary.score}/100**",
        f"- Patients / specimens / assays: {len(manifest.patients)} / "
        f"{len(manifest.specimens)} / {len(manifest.assays)}",
        f"- Findings: {counts['blocker']} blocker, {counts['high']} high, "
        f"{counts['medium']} medium, {counts['low']} low",
        "",
        "## Research question",
        "",
        manifest.objective.question,
        "",
        "## Audit findings",
        "",
    ]
    for finding in audit.findings:
        lines.extend(
            [
                f"### [{finding.severity.upper()}] {finding.code}: {finding.title}",
                "",
                finding.message,
                "",
                f"**Required action:** {finding.remediation}",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation boundary",
            "",
            "This capsule records implemented checks and provenance. It does not certify clinical "
            "validity, regulatory compliance, or fitness for patient care.",
            "",
        ]
    )
    return "\n".join(lines)


def _ro_crate_metadata(manifest: ProjectManifest, contents: dict[str, bytes]) -> bytes:
    file_entities = []
    for name, content in contents.items():
        media_type = "application/json" if name.endswith(".json") else "text/markdown"
        file_entities.append(
            {
                "@id": name,
                "@type": "File",
                "name": name,
                "contentSize": str(len(content)),
                "encodingFormat": media_type,
                "identifier": f"sha256:{hashlib.sha256(content).hexdigest()}",
            }
        )
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
                "name": f"Melinoë Research Capsule: {manifest.title}",
                "description": manifest.description
                or f"Validity-aware research record for {manifest.disease_context}.",
                "datePublished": datetime.now(UTC).date().isoformat(),
                "hasPart": [{"@id": name} for name in contents],
            },
            *file_entities,
        ],
    }
    return _json_bytes(crate)


def build_capsule(
    manifest: ProjectManifest,
    audit: AuditReport,
    snapshot: ResearchSnapshot | None = None,
) -> bytes:
    snapshot = snapshot or build_snapshot(manifest, audit)
    manifest_payload = manifest.model_dump(mode="json")
    audit_payload = audit.model_dump(mode="json")
    manifest_bytes = _json_bytes(manifest_payload)
    audit_bytes = _json_bytes(audit_payload)
    snapshot_bytes = _json_bytes(snapshot.model_dump(mode="json"))
    provenance = {
        "capsule_format": "melinoe-research-capsule/1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "melinoe_version": __version__,
        "python_version": sys.version,
        "platform": platform.platform(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "audit_sha256": hashlib.sha256(audit_bytes).hexdigest(),
        "research_state_sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
        "source_data_included": False,
    }

    contents = {
        "manifest.json": manifest_bytes,
        "audit.json": audit_bytes,
        "research-state.json": snapshot_bytes,
        "provenance.json": _json_bytes(provenance),
        "SUMMARY.md": _summary_markdown(manifest, audit).encode("utf-8"),
    }
    contents["ro-crate-metadata.json"] = _ro_crate_metadata(manifest, contents)
    capsule_index = {
        "format": "melinoe-capsule-index/1.0",
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()},
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
        archive.writestr("capsule-index.json", _json_bytes(capsule_index))
    return buffer.getvalue()


def write_capsule(path: str | Path, manifest: ProjectManifest, audit: AuditReport) -> Path:
    output = Path(path)
    output.write_bytes(build_capsule(manifest, audit))
    return output
