from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

ASSET_ROOT = Path(__file__).resolve().parents[1] / "workflow_assets" / "cohort_native_survival"
REFERENCE_SCRIPT = ASSET_ROOT / "run_reference.R"
USER_SCRIPT = ASSET_ROOT / "run_user_cohorts.R"
REQUIRED_INPUTS = (
    "data_mrna_seq_v2_rsem.txt",
    "data_clinical_patient.txt",
    "data_clinical_sample.txt",
    "GSE85916_series_matrix.txt.gz",
    "GSE57495_series_matrix.txt.gz",
    "GSE62452_series_matrix.txt.gz",
    "GSE164665_Cancer_raw_gene_counts.txt.gz",
    "GSE164665_Stroma_raw_gene_counts.txt.gz",
    "cptac_data_mrna_seq_v2_rsem.txt",
    "cptac_data_protein_quantification.txt",
    "cptac_data_clinical_patient.txt",
    "cptac_data_clinical_sample.txt",
)


class MetricExpectation(BaseModel):
    name: str
    observed: float
    expected: float
    absolute_tolerance: float
    passed: bool


class WorkflowValidationReceipt(BaseModel):
    format_version: str = "melinoe-workflow-validation/1.0"
    workflow_id: str = "bulk-transcriptomics"
    workflow_version: str = "1.0.0"
    benchmark_id: str = "pdac-gprc5a-five-cohort-v2"
    validation_status: str
    validated_at: datetime
    execution_engine: str
    script_sha256: str
    input_manifest_sha256: str | None = None
    patients: int = 0
    events: int = 0
    cohorts: int = 0
    metrics: list[MetricExpectation] = Field(default_factory=list)
    output_sha256: dict[str, str] = Field(default_factory=dict)
    failure_reasons: list[str] = Field(default_factory=list)
    claim_boundary: str = (
        "Computational reference validation only; not clinical validation or therapeutic evidence."
    )


class CohortTableSummary(BaseModel):
    cohorts: int
    patients: int
    events: int
    cohort_counts: dict[str, int]
    cohort_events: dict[str, int]


class WorkflowExecutionReceipt(BaseModel):
    format_version: str = "melinoe-workflow-execution/1.0"
    workflow_id: str = "bulk-transcriptomics"
    workflow_version: str = "1.0.0"
    status: str
    executed_at: datetime
    execution_engine: str
    input_sha256: str
    script_sha256: str
    summary: CohortTableSummary
    output_sha256: dict[str, str]


EXPECTED_METRICS: dict[str, tuple[float, float]] = {
    "patients": (481.0, 0.0),
    "events": (304.0, 0.0),
    "cohorts": (5.0, 0.0),
    "pooled_hr": (1.16231843148536, 1e-6),
    "pooled_ci_low": (0.942041180291319, 1e-6),
    "pooled_ci_high": (1.43410305667614, 1e-6),
    "pooled_p": (0.117784105443416, 1e-6),
    "i2_percent": (28.1540864266008, 1e-4),
    "prediction_low": (0.799974313354491, 1e-6),
    "prediction_high": (1.68878439422082, 1e-6),
    "paired_tumour_adjacent_n": (45.0, 0.0),
    "paired_tumour_adjacent_fold_change": (2.19519839731796, 1e-5),
    "lcm_cancer_stroma_n": (19.0, 0.0),
    "lcm_cancer_stroma_fold_change": (5.66764116518534, 1e-5),
    "rna_protein_n": (135.0, 0.0),
    "rna_protein_spearman": (0.567173934250317, 1e-6),
    "subtype_interaction_p": (0.145587197146821, 1e-6),
    "generic_pooled_hr": (1.16231843148536, 1e-6),
    "generic_tcga_hr": (1.27003607488836, 1e-6),
    "generic_cptac_hr": (0.917573070238538, 1e-6),
    "generic_gse85916_hr": (1.13229876879188, 1e-6),
    "generic_gse57495_hr": (1.39265264296083, 1e-6),
    "generic_gse62452_hr": (1.2421776695035, 1e-6),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _clean_log(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines) + ("\n" if lines else "")


def _collect_observed(result_root: Path) -> tuple[dict[str, float], list[str]]:
    table_root = result_root / "tables"
    required_tables = {
        "cohort_flow": table_root / "cohort_flow.csv",
        "meta": table_root / "random_effects_meta.csv",
        "tumour_adjacent": table_root / "gse62452_tumour_normal.csv",
        "compartment": table_root / "gse164665_lcm_compartment.csv",
        "rna_protein": table_root / "cptac_rna_protein.csv",
        "subtype": table_root / "tcga_subtype_interaction.csv",
        "generic_meta": result_root / "generic_replay" / "random_effects_meta.csv",
        "generic_cox": result_root / "generic_replay" / "cohort_cox_results.csv",
    }
    missing = [
        str(path.relative_to(result_root))
        for path in required_tables.values()
        if not path.is_file()
    ]
    if missing:
        return {}, [f"Missing required output: {name}" for name in missing]

    flow = _read_rows(required_tables["cohort_flow"])
    meta = _read_rows(required_tables["meta"])[0]
    tumour_rows = _read_rows(required_tables["tumour_adjacent"])
    paired = next(row for row in tumour_rows if row["comparison"] == "exact_patient_pairs")
    compartment = _read_rows(required_tables["compartment"])[0]
    rna_protein = _read_rows(required_tables["rna_protein"])[0]
    subtype_rows = _read_rows(required_tables["subtype"])
    interaction = next(row for row in subtype_rows if row["term"] == "gprc5a_z:subtypeClassical")
    generic_meta = _read_rows(required_tables["generic_meta"])[0]
    generic_cox = {row["cohort"]: row for row in _read_rows(required_tables["generic_cox"])}

    observed = {
        "patients": sum(float(row["patients"]) for row in flow),
        "events": sum(float(row["events"]) for row in flow),
        "cohorts": float(len(flow)),
        "pooled_hr": float(meta["hr"]),
        "pooled_ci_low": float(meta["ci_low"]),
        "pooled_ci_high": float(meta["ci_high"]),
        "pooled_p": float(meta["p_value"]),
        "i2_percent": float(meta["i2_percent"]),
        "prediction_low": float(meta["prediction_low"]),
        "prediction_high": float(meta["prediction_high"]),
        "paired_tumour_adjacent_n": float(paired["n_tumour"]),
        "paired_tumour_adjacent_fold_change": float(
            paired["fold_change_from_mean_log2_difference"]
        ),
        "lcm_cancer_stroma_n": float(compartment["pairs"]),
        "lcm_cancer_stroma_fold_change": float(
            compartment["fold_change_from_mean_log2_difference"]
        ),
        "rna_protein_n": float(rna_protein["n"]),
        "rna_protein_spearman": float(rna_protein["spearman_rho"]),
        "subtype_interaction_p": float(interaction["p_value"]),
        "generic_pooled_hr": float(generic_meta["hr"]),
        "generic_tcga_hr": float(generic_cox["TCGA_PAAD"]["hr_per_sd"]),
        "generic_cptac_hr": float(generic_cox["CPTAC_PAAD"]["hr_per_sd"]),
        "generic_gse85916_hr": float(generic_cox["GSE85916"]["hr_per_sd"]),
        "generic_gse57495_hr": float(generic_cox["GSE57495"]["hr_per_sd"]),
        "generic_gse62452_hr": float(generic_cox["GSE62452"]["hr_per_sd"]),
    }
    return observed, []


def validate_reference_outputs(
    result_root: Path,
    *,
    execution_engine: str = "independent result verification",
) -> WorkflowValidationReceipt:
    result_root = result_root.resolve()
    observed, failures = _collect_observed(result_root)
    metrics: list[MetricExpectation] = []
    for name, (expected, tolerance) in EXPECTED_METRICS.items():
        value = observed.get(name, float("nan"))
        passed = name in observed and abs(value - expected) <= tolerance
        metrics.append(
            MetricExpectation(
                name=name,
                observed=value,
                expected=expected,
                absolute_tolerance=tolerance,
                passed=passed,
            )
        )
        if not passed:
            failures.append(f"Reference metric mismatch: {name}")

    output_hashes: dict[str, str] = {}
    if result_root.exists():
        for path in sorted(result_root.rglob("*")):
            if path.is_file() and path.name != "validation-receipt.json":
                output_hashes[path.relative_to(result_root).as_posix()] = _sha256(path)

    input_manifest = result_root / "tables" / "input_manifest.csv"
    return WorkflowValidationReceipt(
        validation_status="passed" if not failures else "failed",
        validated_at=datetime.now(UTC),
        execution_engine=execution_engine,
        script_sha256=_sha256(REFERENCE_SCRIPT),
        input_manifest_sha256=_sha256(input_manifest) if input_manifest.is_file() else None,
        patients=int(observed.get("patients", 0)),
        events=int(observed.get("events", 0)),
        cohorts=int(observed.get("cohorts", 0)),
        metrics=metrics,
        output_sha256=output_hashes,
        failure_reasons=failures,
    )


def preflight_cohort_table(path: Path) -> CohortTableSummary:
    required = {"cohort", "patient_id", "time", "event", "expression"}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
        rows = list(reader)

    cohort_counts: dict[str, int] = {}
    cohort_events: dict[str, int] = {}
    observed_keys: set[tuple[str, str]] = set()
    for line, row in enumerate(rows, start=2):
        cohort = row["cohort"].strip()
        patient = row["patient_id"].strip()
        if not cohort or not patient:
            raise ValueError(f"Line {line}: cohort and patient_id are required")
        key = (cohort, patient)
        if key in observed_keys:
            raise ValueError(f"Line {line}: duplicate patient within cohort: {cohort}/{patient}")
        observed_keys.add(key)
        try:
            time = float(row["time"])
            event = int(row["event"])
            expression = float(row["expression"])
        except ValueError as error:
            raise ValueError(f"Line {line}: non-numeric time, event, or expression") from error
        if not math.isfinite(time) or time <= 0:
            raise ValueError(f"Line {line}: follow-up time must be finite and positive")
        if event not in {0, 1}:
            raise ValueError(f"Line {line}: event must be encoded as 0 or 1")
        if not math.isfinite(expression):
            raise ValueError(f"Line {line}: expression must be finite")
        cohort_counts[cohort] = cohort_counts.get(cohort, 0) + 1
        cohort_events[cohort] = cohort_events.get(cohort, 0) + event

    if len(cohort_counts) < 2:
        raise ValueError("At least two independent cohorts are required")
    for cohort, count in cohort_counts.items():
        if count < 20 or cohort_events[cohort] < 10:
            raise ValueError(f"{cohort} has fewer than 20 patients or 10 events")
    return CohortTableSummary(
        cohorts=len(cohort_counts),
        patients=len(rows),
        events=sum(cohort_events.values()),
        cohort_counts=cohort_counts,
        cohort_events=cohort_events,
    )


def run_cohort_native_survival(
    input_path: Path,
    output_dir: Path,
) -> WorkflowExecutionReceipt:
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    summary = preflight_cohort_table(input_path)
    rscript = shutil.which("Rscript")
    if rscript is None:
        raise RuntimeError("Rscript is required for this validated workflow")
    output_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [rscript, str(USER_SCRIPT), str(input_path), str(output_dir)],
        text=True,
        capture_output=True,
        check=False,
    )
    (output_dir / "workflow.stdout.log").write_text(_clean_log(completed.stdout), encoding="utf-8")
    (output_dir / "workflow.stderr.log").write_text(_clean_log(completed.stderr), encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"Workflow failed with exit code {completed.returncode}; "
            f"inspect {output_dir / 'workflow.stderr.log'}"
        )
    version = subprocess.run([rscript, "--version"], text=True, capture_output=True, check=False)
    output_hashes = {
        path.relative_to(output_dir).as_posix(): _sha256(path)
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "execution-receipt.json"
    }
    receipt = WorkflowExecutionReceipt(
        status="completed",
        executed_at=datetime.now(UTC),
        execution_engine=(version.stderr or version.stdout).strip(),
        input_sha256=_sha256(input_path),
        script_sha256=_sha256(USER_SCRIPT),
        summary=summary,
        output_sha256=output_hashes,
    )
    (output_dir / "execution-receipt.json").write_text(
        receipt.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def run_reference_benchmark(
    workspace: Path,
    *,
    cache_dir: Path | None = None,
    allow_downloads: bool = False,
) -> WorkflowValidationReceipt:
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    cache_dir = (cache_dir or workspace / "data-cache").resolve()
    result_root = workspace / "results"
    cache_dir.mkdir(parents=True, exist_ok=True)
    result_root.mkdir(parents=True, exist_ok=True)

    missing = [name for name in REQUIRED_INPUTS if not (cache_dir / name).is_file()]
    if missing and not allow_downloads:
        raise ValueError("Offline benchmark cache is incomplete. Missing: " + ", ".join(missing))
    rscript = shutil.which("Rscript")
    if rscript is None:
        raise RuntimeError("Rscript is required for this validated workflow")

    environment = os.environ.copy()
    environment["MELINOE_DATA_CACHE"] = str(cache_dir)
    environment["MELINOE_RESULT_DIR"] = str(result_root)
    completed = subprocess.run(
        [rscript, str(REFERENCE_SCRIPT)],
        cwd=workspace,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    (workspace / "benchmark.stdout.log").write_text(_clean_log(completed.stdout), encoding="utf-8")
    (workspace / "benchmark.stderr.log").write_text(_clean_log(completed.stderr), encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"Reference benchmark failed with exit code {completed.returncode}; "
            f"inspect {workspace / 'benchmark.stderr.log'}"
        )

    run_cohort_native_survival(
        result_root / "tables" / "survival_observations.csv",
        result_root / "generic_replay",
    )

    # Reference validation publishes aggregate evidence only. Row-level public
    # records are used locally for the replay, then excluded from the release.
    for row_level_output in (
        "survival_observations.csv",
        "cptac_rna_protein_pairs.csv",
        "gse164665_lcm_pairs.csv",
        "gse62452_exact_pairs.csv",
    ):
        path = result_root / "tables" / row_level_output
        if path.exists():
            path.unlink()

    r_version = subprocess.run([rscript, "--version"], text=True, capture_output=True, check=False)
    engine = (r_version.stderr or r_version.stdout).strip()
    receipt = validate_reference_outputs(result_root, execution_engine=engine)
    receipt_path = result_root / "validation-receipt.json"
    receipt_path.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return receipt


def load_bundled_validation_receipt() -> dict:
    path = ASSET_ROOT / "validation-receipt.json"
    if not path.is_file():
        return {
            "validation_status": "not_bundled",
            "benchmark_id": "pdac-gprc5a-five-cohort-v2",
        }
    return json.loads(path.read_text(encoding="utf-8"))
