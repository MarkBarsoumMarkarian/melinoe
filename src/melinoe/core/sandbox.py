from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from melinoe.core.ledger import AuditLedger


class SandboxPlan(BaseModel):
    engine: str
    workdir: str
    network: str
    command: list[str]


def build_sandbox_command(
    workdir: str | Path,
    command: Sequence[str],
    *,
    network: bool = False,
) -> SandboxPlan:
    binary = shutil.which("bwrap")
    if not binary:
        raise RuntimeError("bubblewrap is unavailable; isolated execution cannot be guaranteed")
    root = Path(workdir).resolve()
    if not root.is_dir():
        raise ValueError(f"work directory does not exist: {root}")
    if not command:
        raise ValueError("a workflow command is required")
    arguments = [
        binary,
        "--ro-bind",
        "/",
        "/",
        "--bind",
        str(root),
        "/mnt",
        "--tmpfs",
        "/tmp",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--unshare-user-try",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--die-with-parent",
        "--new-session",
        "--chdir",
        "/mnt",
    ]
    if not network:
        arguments.append("--unshare-net")
    arguments.extend(["--", *command])
    return SandboxPlan(
        engine="bubblewrap",
        workdir=str(root),
        network="allowed" if network else "denied",
        command=arguments,
    )


def run_sandboxed(
    workdir: str | Path,
    command: Sequence[str],
    *,
    network: bool = False,
    ledger: AuditLedger | None = None,
) -> subprocess.CompletedProcess[str]:
    plan = build_sandbox_command(workdir, command, network=network)
    if ledger:
        ledger.append(
            "workflow.started",
            details={
                "workdir": plan.workdir,
                "network": plan.network,
                "executable": command[0],
                "arguments_count": max(0, len(command) - 1),
            },
        )
    result = subprocess.run(
        plan.command,
        cwd=plan.workdir,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": "/tmp"},
        capture_output=True,
        text=True,
        check=False,
    )
    if ledger:
        ledger.append(
            "workflow.finished",
            details={"executable": command[0], "exit_code": result.returncode},
        )
    return result
