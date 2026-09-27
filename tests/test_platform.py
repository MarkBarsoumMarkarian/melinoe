import json
import shutil
from pathlib import Path

import pytest

from melinoe.core.ledger import AuditLedger
from melinoe.core.policy import ExportPolicy, NetworkPolicy, policy_for
from melinoe.core.sandbox import build_sandbox_command, run_sandboxed
from melinoe.core.snapshot import build_snapshot
from melinoe.core.vault import close_vault, create, open_vault
from melinoe.rules.engine import OncoGuard


def test_sensitivity_policy_is_deterministic() -> None:
    sensitive = policy_for("sensitive")
    controlled = policy_for("controlled")
    opened = policy_for("open")

    assert sensitive.encryption_required is True
    assert sensitive.network == NetworkPolicy.DENY
    assert sensitive.export == ExportPolicy.CAPSULE_ONLY
    assert controlled.network == NetworkPolicy.KNOWLEDGE_ONLY
    assert opened.network == NetworkPolicy.ALLOW
    assert all(not policy.source_data_in_capsules for policy in (sensitive, controlled, opened))


def test_ledger_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger = AuditLedger(path)
    ledger.append("project.created", details={"project": "P1"})
    ledger.append("workflow.finished", details={"exit_code": 0})
    assert ledger.verify().valid is True

    lines = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    event["details"]["project"] = "ALTERED"
    lines[0] = json.dumps(event)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    verification = ledger.verify()
    assert verification.valid is False
    assert verification.error is not None


def test_sandbox_writes_only_inside_selected_project(tmp_path: Path) -> None:
    plan = build_sandbox_command(tmp_path, ["/bin/sh", "-c", "printf ok > result.txt"])
    assert plan.network == "denied"
    assert "--unshare-net" in plan.command

    ledger = AuditLedger(tmp_path / ".melinoe" / "ledger.jsonl")
    result = run_sandboxed(
        tmp_path,
        ["/bin/sh", "-c", "printf ok > result.txt"],
        ledger=ledger,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == "ok"
    assert ledger.verify().event_count == 2


def test_snapshot_can_verify_real_data_file(tmp_path: Path, demo_manifest) -> None:
    data = tmp_path / "assay.dat"
    data.write_bytes(b"melinoe-test-data")
    import hashlib

    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    demo_manifest.assays = [demo_manifest.assays[0]]
    demo_manifest.assays[0].data_path = data.name
    demo_manifest.assays[0].file_sha256 = digest
    report = OncoGuard().audit(demo_manifest)

    state = build_snapshot(demo_manifest, report, base_path=tmp_path, hash_data=True)

    assert state.complete_data_verification is True
    assert state.data_objects[0].checksum_matches is True
    assert state.environment_sha256


@pytest.mark.skipif(
    not (Path(__file__).parents[1] / ".tools" / "bin" / "gocryptfs").exists()
    and not shutil.which("gocryptfs"),
    reason="Project Vault engine is not installed",
)
def test_encrypted_vault_lifecycle(tmp_path: Path) -> None:
    root = tmp_path / "project.vault"
    created = create(root, "integration-test-passphrase")
    assert created.initialized is True
    assert created.mounted is False

    try:
        opened = open_vault(root, "integration-test-passphrase")
        assert opened.mounted is True
        marker = Path(opened.mount_directory) / "proof.txt"
        marker.write_text("encrypted-at-rest", encoding="utf-8")
        assert not any(path.name == "proof.txt" for path in (root / "cipher").rglob("*"))
    finally:
        closed = close_vault(root)
    assert closed.mounted is False
