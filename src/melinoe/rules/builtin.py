from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Any

from melinoe.core.audit import Finding, Severity
from melinoe.core.models import ClaimLevel, ProjectManifest, SplitRole


def _finding(
    code: str,
    title: str,
    severity: Severity,
    message: str,
    remediation: str,
    evidence: list[str] | None = None,
    affected: list[str] | None = None,
) -> Finding:
    return Finding(
        code=code,
        title=title,
        severity=severity,
        message=message,
        evidence=evidence or [],
        remediation=remediation,
        affected_entities=affected or [],
    )


def duplicate_identifiers(manifest: ProjectManifest) -> list[Finding]:
    findings: list[Finding] = []
    collections = {
        "patient": [item.id for item in manifest.patients],
        "specimen": [item.id for item in manifest.specimens],
        "assay": [item.id for item in manifest.assays],
        "endpoint": [item.id for item in manifest.endpoints],
    }
    for entity, identifiers in collections.items():
        duplicates = sorted(key for key, count in Counter(identifiers).items() if count > 1)
        if duplicates:
            findings.append(
                _finding(
                    "OG-001",
                    f"Duplicate {entity} identifiers",
                    Severity.BLOCKER,
                    f"{len(duplicates)} {entity} identifier(s) are not unique.",
                    "Assign a stable unique identifier to every entity before analysis.",
                    [f"Duplicate IDs: {', '.join(duplicates)}"],
                    duplicates,
                )
            )
    return findings


def broken_linkage(manifest: ProjectManifest) -> list[Finding]:
    patient_ids = {patient.id for patient in manifest.patients}
    specimen_ids = {specimen.id for specimen in manifest.specimens}
    evidence: list[str] = []
    affected: list[str] = []
    for specimen in manifest.specimens:
        if specimen.patient_id not in patient_ids:
            evidence.append(
                f"Specimen {specimen.id} references unknown patient {specimen.patient_id}"
            )
            affected.append(specimen.id)
    for assay in manifest.assays:
        if assay.specimen_id not in specimen_ids:
            evidence.append(f"Assay {assay.id} references unknown specimen {assay.specimen_id}")
            affected.append(assay.id)
    for endpoint in manifest.endpoints:
        if endpoint.patient_id not in patient_ids:
            evidence.append(
                f"Endpoint {endpoint.id} references unknown patient {endpoint.patient_id}"
            )
            affected.append(endpoint.id)
    for split in manifest.splits:
        if split.patient_id not in patient_ids:
            evidence.append(f"Split assignment references unknown patient {split.patient_id}")
            affected.append(split.patient_id)
    if not evidence:
        return []
    return [
        _finding(
            "OG-002",
            "Broken patient–specimen–assay linkage",
            Severity.BLOCKER,
            "Some research objects cannot be resolved through the project graph.",
            "Repair every reference and rerun the audit. Unlinked entities cannot enter workflows.",
            evidence,
            affected,
        )
    ]


def patient_split_leakage(manifest: ProjectManifest) -> list[Finding]:
    roles: dict[str, set[str]] = defaultdict(set)
    for assignment in manifest.splits:
        roles[assignment.patient_id].add(assignment.role.value)
    leaked = {patient: sorted(values) for patient, values in roles.items() if len(values) > 1}
    if not leaked:
        return []
    evidence = [f"{patient}: {', '.join(values)}" for patient, values in leaked.items()]
    return [
        _finding(
            "OG-003",
            "Patient leakage across analysis splits",
            Severity.BLOCKER,
            f"{len(leaked)} patient(s) occur in more than one split role.",
            "Assign all material from one patient to exactly one split role.",
            evidence,
            list(leaked),
        )
    ]


def reused_data_paths(manifest: ProjectManifest) -> list[Finding]:
    by_path: dict[str, list[str]] = defaultdict(list)
    for assay in manifest.assays:
        by_path[assay.data_path].append(assay.id)
    reused = {path: ids for path, ids in by_path.items() if path and len(ids) > 1}
    if not reused:
        return []
    return [
        _finding(
            "OG-004",
            "One data object is assigned to multiple assays",
            Severity.HIGH,
            "Reused paths can duplicate observations or attach one measurement to multiple patients.",
            "Confirm whether these are technical replicates; otherwise correct the assay paths.",
            [f"{path}: {', '.join(ids)}" for path, ids in reused.items()],
            [assay_id for ids in reused.values() for assay_id in ids],
        )
    ]


def direct_identifier_risk(manifest: ProjectManifest) -> list[Finding]:
    forbidden = {
        "name",
        "full_name",
        "first_name",
        "last_name",
        "email",
        "phone",
        "address",
        "date_of_birth",
        "dob",
        "medical_record_number",
        "mrn",
    }
    exposed: list[str] = []
    for patient in manifest.patients:
        keys = {key.lower() for key in patient.metadata}
        matches = sorted(keys & forbidden)
        if matches:
            exposed.append(f"Patient {patient.id}: {', '.join(matches)}")
    if not exposed:
        return []
    return [
        _finding(
            "PR-001",
            "Potential direct identifiers in the manifest",
            Severity.BLOCKER,
            "The ordinary project manifest must not contain direct patient identifiers.",
            "Remove direct identifiers and retain the linkage key in an approved, separate location.",
            exposed,
            [entry.split(":", 1)[0].replace("Patient ", "") for entry in exposed],
        )
    ]


def platform_mixing(manifest: ProjectManifest) -> list[Finding]:
    platforms: dict[str, set[str]] = defaultdict(set)
    for assay in manifest.assays:
        if assay.platform:
            platforms[assay.modality.value].add(assay.platform)
    mixed = {modality: sorted(values) for modality, values in platforms.items() if len(values) > 1}
    if not mixed:
        return []
    if manifest.settings.allow_platform_mixing and manifest.settings.platform_mixing_justification:
        severity = Severity.INFO
        message = "Multiple platforms are declared with an explicit project justification."
    else:
        severity = Severity.HIGH
        message = "Multiple measurement platforms occur within at least one modality without a declared strategy."
    return [
        _finding(
            "AS-001",
            "Cross-platform measurements require an explicit strategy",
            severity,
            message,
            "Separate platform-native analyses or document and validate the harmonization strategy.",
            [f"{modality}: {', '.join(values)}" for modality, values in mixed.items()],
        )
    ]


def missing_batch_metadata(manifest: ProjectManifest) -> list[Finding]:
    affected = [assay.id for assay in manifest.assays if not assay.batch]
    if not affected:
        return []
    fraction = len(affected) / max(len(manifest.assays), 1)
    severity = Severity.HIGH if fraction >= 0.5 else Severity.MEDIUM
    return [
        _finding(
            "AS-002",
            "Batch metadata are incomplete",
            severity,
            f"{len(affected)} of {len(manifest.assays)} assays have no batch assignment.",
            "Recover processing batch, centre, plate, run, or slide information before modelling.",
            [f"Assays without batch: {', '.join(affected)}"],
            affected,
        )
    ]


def batch_outcome_confounding(manifest: ProjectManifest) -> list[Finding]:
    outcome_key = manifest.objective.primary_outcome
    if not outcome_key:
        return []
    strata: dict[tuple[str, str], list[tuple[str, Any]]] = defaultdict(list)
    for assay in manifest.assays:
        patient = manifest.patient_for_assay(assay)
        if patient is None or not assay.batch or outcome_key not in patient.metadata:
            continue
        strata[(assay.modality.value, assay.batch)].append(
            (patient.id, patient.metadata[outcome_key])
        )

    by_modality: dict[str, list[tuple[str, set[str], int]]] = defaultdict(list)
    for (modality, batch), observations in strata.items():
        labels = {str(label) for _, label in observations}
        by_modality[modality].append((batch, labels, len(observations)))

    evidence: list[str] = []
    for modality, batches in by_modality.items():
        all_labels = set().union(*(labels for _, labels, _ in batches)) if batches else set()
        if (
            len(batches) >= 2
            and len(all_labels) >= 2
            and all(len(labels) == 1 for _, labels, _ in batches)
        ):
            details = "; ".join(
                f"batch {batch} = {next(iter(labels))} (n={count})"
                for batch, labels, count in batches
            )
            evidence.append(f"{modality}: {details}")
    if not evidence:
        return []
    return [
        _finding(
            "AS-003",
            "Outcome is perfectly separated by batch",
            Severity.BLOCKER,
            f"The declared outcome '{outcome_key}' cannot be distinguished from batch in at least one modality.",
            "Obtain overlap between outcomes and batches, use an independent cohort, or narrow the claim. Statistical adjustment cannot recover absent overlap.",
            evidence,
        )
    ]


def survival_event_support(manifest: ProjectManifest) -> list[Finding]:
    survival = [endpoint for endpoint in manifest.endpoints if endpoint.time is not None]
    if not survival:
        return []
    incomplete = [
        endpoint.id for endpoint in survival if endpoint.event is None or endpoint.time_unit is None
    ]
    findings: list[Finding] = []
    if incomplete:
        findings.append(
            _finding(
                "EP-001",
                "Incomplete time-to-event endpoints",
                Severity.BLOCKER,
                "Some time-to-event records lack event status or time units.",
                "Define event semantics and a common time unit for every survival record.",
                [f"Incomplete endpoints: {', '.join(incomplete)}"],
                incomplete,
            )
        )
    events = sum(endpoint.event is True for endpoint in survival)
    if events < manifest.settings.minimum_survival_events:
        findings.append(
            _finding(
                "EP-002",
                "Insufficient observed events for the intended survival analysis",
                Severity.HIGH,
                f"Only {events} event(s) are recorded; the project minimum is {manifest.settings.minimum_survival_events}.",
                "Increase follow-up or cohort size, simplify the model, and report the analysis as underpowered if it proceeds.",
                [f"Events={events}", f"Time-to-event records={len(survival)}"],
            )
        )
    return findings


def locked_test_support(manifest: ProjectManifest) -> list[Finding]:
    locked = {split.patient_id for split in manifest.splits if split.role == SplitRole.LOCKED_TEST}
    if not locked:
        return [
            _finding(
                "EV-001",
                "No locked test cohort is declared",
                Severity.HIGH,
                "Predictive performance cannot be treated as a final test without a patient-locked cohort.",
                "Reserve a patient-level test cohort before feature selection or model tuning.",
            )
        ]
    if len(locked) < manifest.settings.minimum_locked_test_patients:
        return [
            _finding(
                "EV-002",
                "Locked test cohort is smaller than the declared minimum",
                Severity.HIGH,
                f"The locked test contains {len(locked)} patients; the project minimum is {manifest.settings.minimum_locked_test_patients}.",
                "Increase the independent test cohort or narrow the intended performance claim.",
                [f"Locked patients: {', '.join(sorted(locked))}"],
                sorted(locked),
            )
        ]
    return []


def claim_evidence_alignment(manifest: ProjectManifest) -> list[Finding]:
    claim = manifest.objective.intended_claim_level
    external = {
        split.patient_id for split in manifest.splits if split.role == SplitRole.EXTERNAL_VALIDATION
    }
    if (
        claim
        in {
            ClaimLevel.EXTERNAL_VALIDATION,
            ClaimLevel.BIOLOGICAL_SUPPORT,
            ClaimLevel.CLINICAL_UTILITY,
        }
        and not external
    ):
        return [
            _finding(
                "CL-001",
                "Intended claim exceeds the declared validation design",
                Severity.BLOCKER,
                f"The intended claim level is '{claim.value}', but no external-validation cohort is declared.",
                "Add a genuinely independent cohort or reduce the intended claim level.",
            )
        ]
    if claim == ClaimLevel.CLINICAL_UTILITY:
        return [
            _finding(
                "CL-002",
                "Clinical-utility claims require evidence outside this workbench",
                Severity.HIGH,
                "A computational project manifest cannot by itself establish clinical utility.",
                "Define prospective evaluation, clinical comparators, intended use, and appropriate regulatory and ethical review.",
            )
        ]
    return []


def missing_checksums(manifest: ProjectManifest) -> list[Finding]:
    affected = [assay.id for assay in manifest.assays if not assay.file_sha256]
    if not affected:
        return []
    return [
        _finding(
            "PV-001",
            "Input checksums are missing",
            Severity.MEDIUM,
            f"{len(affected)} assay input(s) cannot yet be content-verified.",
            "Calculate SHA-256 checksums when files are imported into the project.",
            [f"Assays without checksums: {', '.join(affected)}"],
            affected,
        )
    ]


def modality_inventory(manifest: ProjectManifest) -> list[Finding]:
    counts = Counter(assay.modality.value for assay in manifest.assays)
    if not counts:
        return [
            _finding(
                "IN-001",
                "No assay data are registered",
                Severity.BLOCKER,
                "The project has no assay objects.",
                "Import at least one assay and link it to a specimen and patient.",
            )
        ]
    return [
        _finding(
            "IN-002",
            "Multimodal inventory",
            Severity.INFO,
            f"The project contains {len(counts)} assay modality or modalities.",
            "Review the inventory before choosing workflows.",
            [f"{modality}: {count}" for modality, count in sorted(counts.items())],
        )
    ]


BUILTIN_RULES: list[tuple[str, Callable[[ProjectManifest], list[Finding]]]] = [
    ("OG-001", duplicate_identifiers),
    ("OG-002", broken_linkage),
    ("OG-003", patient_split_leakage),
    ("OG-004", reused_data_paths),
    ("PR-001", direct_identifier_risk),
    ("AS-001", platform_mixing),
    ("AS-002", missing_batch_metadata),
    ("AS-003", batch_outcome_confounding),
    ("EP-001/EP-002", survival_event_support),
    ("EV-001/EV-002", locked_test_support),
    ("CL-001/CL-002", claim_evidence_alignment),
    ("PV-001", missing_checksums),
    ("IN-001/IN-002", modality_inventory),
]
