from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from melinoe import __version__
from melinoe.core.capsule import build_capsule
from melinoe.core.knowledge import KnowledgeManifest
from melinoe.core.models import ProjectManifest
from melinoe.core.policy import policy_for
from melinoe.core.snapshot import build_snapshot
from melinoe.core.system import system_profile
from melinoe.core.workflow_benchmark import load_bundled_validation_receipt
from melinoe.core.workflow_lock import SignedWorkflowLock, WorkflowLock
from melinoe.core.workflows import WORKFLOW_REGISTRY, get_workflow, plan_workflow
from melinoe.rules.engine import OncoGuard

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_DEMO_PATH = PROJECT_ROOT / "examples" / "multimodal_demo" / "project.json"
PACKAGED_DEMO_PATH = PACKAGE_ROOT / "data" / "multimodal_demo.json"
DEMO_PATH = SOURCE_DEMO_PATH if SOURCE_DEMO_PATH.exists() else PACKAGED_DEMO_PATH
WEB_PATH = PACKAGE_ROOT / "web"

app = FastAPI(
    title="Melinoë Local API",
    version=__version__,
    description="Local-first validity services for multimodal cancer research.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

guard = OncoGuard()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/schema")
def schema() -> dict:
    return ProjectManifest.model_json_schema()


@app.get("/api/formats")
def formats() -> dict:
    return {
        "project_manifest": "1.0",
        "research_state": "1.0",
        "research_capsule": "1.0 + RO-Crate 1.3",
        "workflow_lock": "1.0",
        "knowledge_pack": "1.0",
        "checkpoint": "1.0",
        "hpc_handoff": "1.0 + RO-Crate 1.3",
        "workflow_validation": "1.0",
    }


@app.get("/api/formats/workflow-lock")
def workflow_lock_schema() -> dict:
    return {
        "lock": WorkflowLock.model_json_schema(),
        "signed": SignedWorkflowLock.model_json_schema(),
    }


@app.get("/api/formats/knowledge-pack")
def knowledge_pack_schema() -> dict:
    return KnowledgeManifest.model_json_schema()


@app.get("/api/system")
def system() -> dict:
    return system_profile(PROJECT_ROOT).model_dump(mode="json")


@app.get("/api/policy/{sensitivity}")
def policy(sensitivity: str) -> dict:
    try:
        return policy_for(sensitivity).model_dump(mode="json")
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Unknown sensitivity level") from error


@app.get("/api/demo", response_model=ProjectManifest)
def demo() -> ProjectManifest:
    if not DEMO_PATH.exists():
        raise HTTPException(status_code=404, detail="Bundled demo project is unavailable")
    return ProjectManifest.from_json_file(DEMO_PATH)


@app.post("/api/audit")
def audit(manifest: ProjectManifest) -> dict:
    return guard.audit(manifest).model_dump(mode="json")


@app.post("/api/capsule")
def capsule(manifest: ProjectManifest) -> Response:
    report = guard.audit(manifest)
    payload = build_capsule(manifest, report)
    filename = f"{manifest.project_id}-research-capsule.zip"
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/snapshot")
def snapshot(manifest: ProjectManifest) -> dict:
    report = guard.audit(manifest)
    return build_snapshot(manifest, report).model_dump(mode="json")


@app.get("/api/workflows")
def workflows() -> list[dict]:
    return [workflow.model_dump(mode="json") for workflow in WORKFLOW_REGISTRY]


@app.post("/api/workflows/{workflow_id}/plan")
def workflow_plan(workflow_id: str, manifest: ProjectManifest) -> dict:
    try:
        get_workflow(workflow_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown workflow") from error
    report = guard.audit(manifest)
    return plan_workflow(manifest, report, workflow_id).model_dump(mode="json")


@app.get("/api/workflows/{workflow_id}/evidence")
def workflow_evidence(workflow_id: str) -> dict:
    try:
        workflow = get_workflow(workflow_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown workflow") from error
    if workflow.validation is None:
        raise HTTPException(status_code=404, detail="Workflow has no completed validation")
    return load_bundled_validation_receipt()


if WEB_PATH.exists():
    app.mount("/", StaticFiles(directory=WEB_PATH, html=True), name="workbench")


def create_app() -> FastAPI:
    return app
