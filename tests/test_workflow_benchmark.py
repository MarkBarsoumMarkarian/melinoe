from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from melinoe.core.workflow_benchmark import (
    EXPECTED_METRICS,
    preflight_cohort_table,
    run_reference_benchmark,
    validate_reference_outputs,
)
from melinoe.core.workflows import WorkflowMaturity, get_workflow

REFERENCE_RESULTS = (
    Path(__file__).parents[1] / "validation" / "gold_studies" / "pdac_gprc5a_v2" / "results"
)


def test_gold_study_receipt_passes_all_reference_checks() -> None:
    receipt = validate_reference_outputs(REFERENCE_RESULTS)
    assert receipt.validation_status == "passed"
    assert receipt.patients == 481
    assert receipt.events == 304
    assert receipt.cohorts == 5
    assert len(receipt.metrics) == len(EXPECTED_METRICS) == 23
    assert all(metric.passed for metric in receipt.metrics)

    workflow = get_workflow("bulk-transcriptomics")
    assert workflow.maturity == WorkflowMaturity.VALIDATED
    assert workflow.validation is not None
    assert workflow.validation.benchmark_id == receipt.benchmark_id


def test_gold_study_verifier_rejects_tampered_scientific_result(tmp_path: Path) -> None:
    tampered = tmp_path / "results"
    shutil.copytree(REFERENCE_RESULTS, tampered)
    meta_path = tampered / "tables" / "random_effects_meta.csv"
    with meta_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    rows[0]["hr"] = "9.9"
    with meta_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    receipt = validate_reference_outputs(tampered)
    assert receipt.validation_status == "failed"
    assert "Reference metric mismatch: pooled_hr" in receipt.failure_reasons


def test_reference_runner_is_offline_by_default(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Offline benchmark cache is incomplete"):
        run_reference_benchmark(tmp_path / "workspace", cache_dir=tmp_path / "empty-cache")


def test_user_cohort_contract_rejects_patient_duplication(tmp_path: Path) -> None:
    source = tmp_path / "cohorts.csv"
    rows = ["cohort,patient_id,time,event,expression"]
    for cohort in ("A", "B"):
        for index in range(20):
            rows.append(
                f"{cohort},{cohort}{index:02d},{index + 1},{int(index % 2 == 0)},{index / 3}"
            )
    source.write_text("\n".join(rows) + "\n", encoding="utf-8")
    valid = preflight_cohort_table(source)
    assert valid.cohorts == 2
    assert valid.patients == 40

    duplicated = tmp_path / "duplicate.csv"
    content = source.read_text(encoding="utf-8")
    first_data_row = content.splitlines()[1]
    duplicated.write_text(content + first_data_row + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate patient within cohort"):
        preflight_cohort_table(duplicated)
