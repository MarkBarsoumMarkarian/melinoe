from __future__ import annotations

import getpass
import json
import shlex
from pathlib import Path

import typer

from melinoe.core.capsule import write_capsule
from melinoe.core.checkpoints import (
    create_checkpoint,
    list_checkpoints,
    restore_checkpoint,
)
from melinoe.core.handoff import SlurmProfile, build_hpc_handoff, verify_hpc_handoff
from melinoe.core.knowledge import (
    KnowledgeManifest,
    build_knowledge_pack,
    install_knowledge_pack,
    list_knowledge_packs,
    verify_knowledge_pack,
)
from melinoe.core.ledger import AuditLedger
from melinoe.core.models import ProjectManifest
from melinoe.core.sandbox import run_sandboxed
from melinoe.core.signing import generate_signing_key
from melinoe.core.snapshot import build_snapshot
from melinoe.core.system import system_profile
from melinoe.core.vault import close_vault, create, open_vault, status
from melinoe.core.workflow_benchmark import (
    run_cohort_native_survival,
    run_reference_benchmark,
    validate_reference_outputs,
)
from melinoe.core.workflow_lock import SignedWorkflowLock, WorkflowLock, sign_workflow_lock
from melinoe.core.workflows import WORKFLOW_REGISTRY, get_workflow, plan_workflow
from melinoe.rules.engine import OncoGuard

app = typer.Typer(
    name="melinoe",
    help="Local-first, validity-aware cancer-research workbench.",
    no_args_is_help=True,
)
vault_app = typer.Typer(help="Create, unlock, lock, and inspect encrypted Project Vaults.")
ledger_app = typer.Typer(help="Inspect the tamper-evident local research ledger.")
keys_app = typer.Typer(help="Manage offline workflow and knowledge signing keys.")
workflow_app = typer.Typer(help="Sign and verify immutable workflow locks.")
fabric_app = typer.Typer(help="Plan, inspect, and validate executable cancer workflows.")
knowledge_app = typer.Typer(help="Build, verify, and install offline knowledge packs.")
checkpoint_app = typer.Typer(help="Create and restore verified project checkpoints.")
app.add_typer(vault_app, name="vault")
app.add_typer(ledger_app, name="ledger")
app.add_typer(keys_app, name="keys")
app.add_typer(workflow_app, name="workflow-lock")
app.add_typer(fabric_app, name="workflow")
app.add_typer(knowledge_app, name="knowledge")
app.add_typer(checkpoint_app, name="checkpoint")


@app.command()
def audit(
    manifest: Path = typer.Argument(..., exists=True, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Audit a Melinoë project manifest with OncoGuard."""
    project = ProjectManifest.from_json_file(manifest)
    report = OncoGuard().audit(project)
    payload = json.dumps(report.model_dump(mode="json"), indent=2)
    if output:
        output.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"Audit written to {output}")
    else:
        typer.echo(payload)
    if report.summary.status == "blocked":
        raise typer.Exit(code=2)


@app.command()
def capsule(
    manifest: Path = typer.Argument(..., exists=True, readable=True),
    output: Path = typer.Option(Path("research-capsule.zip"), "--output", "-o"),
) -> None:
    """Export a portable Research Capsule."""
    project = ProjectManifest.from_json_file(manifest)
    report = OncoGuard().audit(project)
    write_capsule(output, project, report)
    typer.echo(f"Research Capsule written to {output}")


@app.command()
def snapshot(
    manifest: Path = typer.Argument(..., exists=True, readable=True),
    output: Path = typer.Option(Path("research-state.json"), "--output", "-o"),
    hash_data: bool = typer.Option(False, help="Read and hash every registered data file."),
) -> None:
    """Freeze the project, environment, policy, hardware, and data-file state."""
    project = ProjectManifest.from_json_file(manifest)
    report = OncoGuard().audit(project)
    state = build_snapshot(
        project,
        report,
        base_path=manifest.parent,
        hash_data=hash_data,
    )
    output.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Research state written to {output}")
    if hash_data and not state.complete_data_verification:
        raise typer.Exit(code=2)


@app.command("system")
def show_system() -> None:
    """Inspect local compute, encryption, and isolation capabilities."""
    typer.echo(system_profile().model_dump_json(indent=2))


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def isolate(
    context: typer.Context,
    workdir: Path = typer.Argument(..., exists=True, file_okay=False, resolve_path=True),
    network: bool = typer.Option(False, help="Explicitly retain host network access."),
) -> None:
    """Run a command inside a project-only, network-denied sandbox."""
    command = list(context.args)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise typer.BadParameter("pass a command after --")
    ledger = AuditLedger(workdir / ".melinoe" / "ledger.jsonl")
    result = run_sandboxed(workdir, command, network=network, ledger=ledger)
    if result.stdout:
        typer.echo(result.stdout, nl=False)
    if result.stderr:
        typer.echo(result.stderr, err=True, nl=False)
    raise typer.Exit(code=result.returncode)


@vault_app.command("status")
def vault_status(root: Path) -> None:
    """Inspect an encrypted Project Vault."""
    typer.echo(status(root).model_dump_json(indent=2))


@vault_app.command("create")
def vault_create(root: Path) -> None:
    """Create an encrypted Project Vault without putting the passphrase in shell history."""
    password = getpass.getpass("Vault passphrase: ")
    confirmation = getpass.getpass("Confirm passphrase: ")
    if password != confirmation:
        raise typer.BadParameter("passphrases do not match")
    created = create(root, password)
    typer.echo(f"Project Vault created at {created.root}")
    typer.echo("Back up cipher/gocryptfs.conf separately; data cannot be recovered without it.")


@vault_app.command("open")
def vault_open(root: Path) -> None:
    """Unlock a Project Vault."""
    opened = open_vault(root, getpass.getpass("Vault passphrase: "))
    typer.echo(f"Project Vault available at {opened.mount_directory}")


@vault_app.command("close")
def vault_close(root: Path) -> None:
    """Lock a Project Vault."""
    closed = close_vault(root)
    typer.echo(f"Project Vault locked: {closed.root}")


@ledger_app.command("verify")
def ledger_verify(path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Verify every event and link in a Melinoë audit ledger."""
    verification = AuditLedger(path).verify()
    typer.echo(verification.model_dump_json(indent=2))
    if not verification.valid:
        raise typer.Exit(code=2)


@keys_app.command("create")
def keys_create(
    private_key: Path = typer.Option(Path("melinoe-signing-key.pem"), "--private"),
    public_key: Path = typer.Option(Path("melinoe-signing-key.pub"), "--public"),
) -> None:
    """Create an encrypted Ed25519 signing key and its shareable public key."""
    passphrase = getpass.getpass("Signing-key passphrase: ")
    confirmation = getpass.getpass("Confirm passphrase: ")
    if passphrase != confirmation:
        raise typer.BadParameter("passphrases do not match")
    key_id = generate_signing_key(private_key, public_key, passphrase)
    typer.echo(f"Signing key created. Key ID: {key_id}")


@workflow_app.command("sign")
def workflow_sign(
    lock_file: Path = typer.Argument(..., exists=True, readable=True),
    private_key: Path = typer.Option(..., "--key", exists=True, readable=True),
    output: Path = typer.Option(Path("signed-workflow-lock.json"), "--output", "-o"),
) -> None:
    """Sign a validated, digest-pinned workflow lock for execution."""
    lock = WorkflowLock.model_validate_json(lock_file.read_text(encoding="utf-8"))
    signed = sign_workflow_lock(lock, str(private_key), getpass.getpass("Key passphrase: "))
    output.write_text(signed.model_dump_json(indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Signed workflow lock written to {output}")


@workflow_app.command("verify")
def workflow_verify(path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Verify a signed workflow lock offline."""
    signed = SignedWorkflowLock.model_validate_json(path.read_text(encoding="utf-8"))
    valid = signed.verify()
    typer.echo(json.dumps({"valid": valid, "key_id": signed.signature.key_id}, indent=2))
    if not valid:
        raise typer.Exit(code=2)


@fabric_app.command("list")
def workflow_list() -> None:
    """List workflow maturity and validation evidence."""
    typer.echo(
        json.dumps(
            [workflow.model_dump(mode="json") for workflow in WORKFLOW_REGISTRY],
            indent=2,
        )
    )


@fabric_app.command("plan")
def workflow_plan_command(
    workflow_id: str = typer.Argument(...),
    manifest: Path = typer.Argument(..., exists=True, readable=True),
) -> None:
    """Evaluate a project against a workflow's scientific and policy gates."""
    try:
        get_workflow(workflow_id)
    except KeyError as error:
        raise typer.BadParameter("unknown workflow") from error
    project = ProjectManifest.from_json_file(manifest)
    plan = plan_workflow(project, OncoGuard().audit(project), workflow_id)
    typer.echo(plan.model_dump_json(indent=2))
    if plan.status != "ready":
        raise typer.Exit(code=2)


@fabric_app.command("benchmark")
def workflow_benchmark(
    workflow_id: str = typer.Argument(...),
    workspace: Path = typer.Option(Path("melinoe-benchmark"), "--workspace", "-w"),
    cache: Path | None = typer.Option(None, "--cache"),
    allow_downloads: bool = typer.Option(
        False,
        "--allow-downloads",
        help="Fetch the checksummed public reference inputs when the cache is incomplete.",
    ),
) -> None:
    """Execute a workflow's complete public reference benchmark."""
    if workflow_id != "bulk-transcriptomics":
        raise typer.BadParameter("this workflow does not yet have an executable benchmark")
    receipt = run_reference_benchmark(
        workspace,
        cache_dir=cache,
        allow_downloads=allow_downloads,
    )
    typer.echo(receipt.model_dump_json(indent=2))
    if receipt.validation_status != "passed":
        raise typer.Exit(code=2)


@fabric_app.command("run")
def workflow_run(
    workflow_id: str = typer.Argument(...),
    cohort_table: Path = typer.Argument(..., exists=True, readable=True),
    output: Path = typer.Option(Path("melinoe-results"), "--output", "-o"),
) -> None:
    """Run a validated workflow on a strict cohort-level input table."""
    if workflow_id != "bulk-transcriptomics":
        raise typer.BadParameter("this workflow does not yet have a project-data executor")
    receipt = run_cohort_native_survival(cohort_table, output)
    typer.echo(receipt.model_dump_json(indent=2))


@fabric_app.command("verify-results")
def workflow_verify_results(
    workflow_id: str = typer.Argument(...),
    result_root: Path = typer.Argument(..., exists=True, file_okay=False),
) -> None:
    """Independently compare workflow outputs with the frozen reference benchmark."""
    if workflow_id != "bulk-transcriptomics":
        raise typer.BadParameter("this workflow does not yet have reference expectations")
    receipt = validate_reference_outputs(result_root)
    typer.echo(receipt.model_dump_json(indent=2))
    if receipt.validation_status != "passed":
        raise typer.Exit(code=2)


@knowledge_app.command("build")
def knowledge_build(
    source: Path = typer.Argument(..., exists=True, file_okay=False),
    metadata: Path = typer.Argument(..., exists=True, readable=True),
    private_key: Path = typer.Option(..., "--key", exists=True, readable=True),
    output: Path = typer.Option(Path("knowledge.mknowledge"), "--output", "-o"),
) -> None:
    """Build and sign a versioned offline knowledge pack."""
    manifest = KnowledgeManifest.model_validate_json(metadata.read_text(encoding="utf-8"))
    build_knowledge_pack(
        source,
        manifest,
        output,
        private_key,
        getpass.getpass("Key passphrase: "),
    )
    typer.echo(f"Knowledge pack written to {output}")


@knowledge_app.command("verify")
def knowledge_verify(path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Verify an offline knowledge pack signature and every contained file."""
    verification = verify_knowledge_pack(path)
    typer.echo(verification.model_dump_json(indent=2))
    if not verification.valid:
        raise typer.Exit(code=2)


@knowledge_app.command("install")
def knowledge_install(
    path: Path = typer.Argument(..., exists=True, readable=True),
    registry: Path = typer.Option(..., "--registry"),
) -> None:
    """Install a verified pack into a content-addressed offline registry."""
    destination = install_knowledge_pack(path, registry)
    typer.echo(f"Knowledge pack installed at {destination}")


@knowledge_app.command("list")
def knowledge_list(registry: Path = typer.Option(..., "--registry")) -> None:
    """List and re-verify installed offline knowledge packs."""
    typer.echo(
        json.dumps(
            [item.model_dump(mode="json") for item in list_knowledge_packs(registry)],
            indent=2,
            default=str,
        )
    )


@checkpoint_app.command("create")
def checkpoint_create(
    project_root: Path = typer.Argument(..., exists=True, file_okay=False),
    manifest: Path = typer.Option(..., "--manifest", exists=True, readable=True),
) -> None:
    """Create an atomic, checksummed control-plane checkpoint without copying source data."""
    project = ProjectManifest.from_json_file(manifest)
    report = OncoGuard().audit(project)
    state = build_snapshot(project, report, base_path=manifest.parent)
    destination = create_checkpoint(project_root, project, report, state)
    typer.echo(f"Checkpoint created: {destination.name}")


@checkpoint_app.command("list")
def checkpoint_list(project_root: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """List verified project checkpoints."""
    typer.echo(
        json.dumps(
            [item.model_dump(mode="json") for item in list_checkpoints(project_root)],
            indent=2,
            default=str,
        )
    )


@checkpoint_app.command("restore")
def checkpoint_restore(
    project_root: Path = typer.Argument(..., exists=True, file_okay=False),
    checkpoint_id: str = typer.Argument(...),
    manifest: Path = typer.Option(..., "--manifest"),
) -> None:
    """Restore a verified manifest while preserving the current manifest as a backup."""
    backup = restore_checkpoint(project_root, checkpoint_id, manifest)
    typer.echo(f"Checkpoint restored to {manifest}")
    if backup:
        typer.echo(f"Previous manifest preserved at {backup}")


@app.command("hpc-handoff")
def hpc_handoff(
    manifest: Path = typer.Argument(..., exists=True, readable=True),
    signed_lock: Path = typer.Argument(..., exists=True, readable=True),
    output: Path = typer.Option(Path("hpc-handoff.zip"), "--output", "-o"),
    private_key: Path = typer.Option(..., "--key", exists=True, readable=True),
    partition: str | None = typer.Option(None),
    account: str | None = typer.Option(None),
    network_isolator: str | None = typer.Option(
        None,
        help="Cluster-approved command prefix that creates a network-denied namespace.",
    ),
) -> None:
    """Build a validity-gated, signed, digest-pinned Slurm handoff bundle."""
    project = ProjectManifest.from_json_file(manifest)
    report = OncoGuard().audit(project)
    state = build_snapshot(project, report, base_path=manifest.parent)
    lock = SignedWorkflowLock.model_validate_json(signed_lock.read_text(encoding="utf-8"))
    profile = SlurmProfile(
        partition=partition,
        account=account,
        network_isolation_command=shlex.split(network_isolator) if network_isolator else None,
    )
    build_hpc_handoff(
        project,
        report,
        state,
        lock,
        output,
        profile,
        private_key,
        getpass.getpass("Handoff signing-key passphrase: "),
    )
    typer.echo(f"HPC handoff written to {output}")


@app.command("hpc-verify")
def hpc_verify(path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Verify a handoff signature, every file, and the embedded workflow lock."""
    verification = verify_hpc_handoff(path)
    typer.echo(verification.model_dump_json(indent=2))
    if not verification.valid:
        raise typer.Exit(code=2)


@app.command()
def schema(output: Path | None = typer.Option(None, "--output", "-o")) -> None:
    """Print the current OncoGraph JSON schema."""
    payload = json.dumps(ProjectManifest.model_json_schema(), indent=2)
    if output:
        output.write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"Schema written to {output}")
    else:
        typer.echo(payload)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8787),
    reload: bool = typer.Option(False),
) -> None:
    """Launch the local Melinoë workbench."""
    import uvicorn

    uvicorn.run("melinoe.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
