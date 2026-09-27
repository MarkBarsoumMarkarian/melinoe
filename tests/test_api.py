from fastapi.testclient import TestClient

from melinoe.api.app import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_system_and_policy_are_exposed() -> None:
    system_response = client.get("/api/system")
    assert system_response.status_code == 200
    system = system_response.json()
    assert system["compute"]["logical_cpus"] >= 1
    assert "sandbox" in system["capabilities"]

    policy_response = client.get("/api/policy/sensitive")
    assert policy_response.status_code == 200
    policy = policy_response.json()
    assert policy["encryption_required"] is True
    assert policy["network"] == "deny"
    assert policy["source_data_in_capsules"] is False

    assert client.get("/api/policy/secretish").status_code == 404

    formats_response = client.get("/api/formats")
    assert formats_response.status_code == 200
    assert formats_response.json()["hpc_handoff"] == "1.0 + RO-Crate 1.3"
    assert formats_response.json()["workflow_validation"] == "1.0"
    assert client.get("/api/formats/workflow-lock").status_code == 200


def test_demo_can_be_audited_and_exported() -> None:
    demo_response = client.get("/api/demo")
    assert demo_response.status_code == 200

    audit_response = client.post("/api/audit", json=demo_response.json())
    assert audit_response.status_code == 200
    assert audit_response.json()["summary"]["status"] == "blocked"

    capsule_response = client.post("/api/capsule", json=demo_response.json())
    assert capsule_response.status_code == 200
    assert capsule_response.headers["content-type"] == "application/zip"
    assert len(capsule_response.content) > 1000

    snapshot_response = client.post("/api/snapshot", json=demo_response.json())
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["project_id"] == "melinoe_multimodal_demo"


def test_workflow_planning_is_enforced_by_the_api() -> None:
    demo = client.get("/api/demo").json()
    registry_response = client.get("/api/workflows")
    assert registry_response.status_code == 200
    assert len(registry_response.json()) == 6
    assert registry_response.json()[0]["maturity"] == "validated"
    assert registry_response.json()[0]["validation"]["patients"] == 481

    evidence_response = client.get("/api/workflows/bulk-transcriptomics/evidence")
    assert evidence_response.status_code == 200
    assert evidence_response.json()["validation_status"] == "passed"
    assert len(evidence_response.json()["metrics"]) == 23
    assert client.get("/api/workflows/digital-pathology/evidence").status_code == 404

    plan_response = client.post("/api/workflows/bulk-transcriptomics/plan", json=demo)
    assert plan_response.status_code == 200
    plan = plan_response.json()
    assert plan["status"] == "blocked"
    assert "AS-003" in plan["blocking_finding_codes"]
    assert len(plan["matched_assay_ids"]) == 8
    assert plan["project_policy"]["network"] == "deny"
    assert plan["project_policy"]["encryption_required"] is True

    missing_response = client.post("/api/workflows/not-a-workflow/plan", json=demo)
    assert missing_response.status_code == 404
