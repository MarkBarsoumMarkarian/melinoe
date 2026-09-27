from __future__ import annotations

import os
import platform
import shutil
import subprocess
from importlib.metadata import version
from pathlib import Path

from pydantic import BaseModel, Field


class ToolCapability(BaseModel):
    available: bool
    path: str | None = None
    version: str | None = None
    operational: bool | None = None
    detail: str | None = None


class ComputeProfile(BaseModel):
    architecture: str
    cpu_model: str
    logical_cpus: int
    memory_bytes: int
    disk_free_bytes: int
    gpu: str | None = None
    gpu_memory_bytes: int | None = None
    recommended_tier: str


class SystemProfile(BaseModel):
    os: str
    kernel: str
    compute: ComputeProfile
    capabilities: dict[str, ToolCapability] = Field(default_factory=dict)
    offline_execution_ready: bool
    encrypted_vault_ready: bool


def _run(command: list[str], timeout: float = 3) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def _version(binary: str, *arguments: str) -> ToolCapability:
    path = shutil.which(binary)
    if not path:
        return ToolCapability(available=False)
    try:
        result = _run([path, *arguments])
        text = (result.stdout or result.stderr).strip().splitlines()
        return ToolCapability(
            available=True,
            path=path,
            version=text[0] if text else None,
            operational=result.returncode == 0,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return ToolCapability(available=True, path=path, operational=False, detail=str(error))


def _memory_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024
    return 0


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "Unknown CPU"


def _gpu() -> tuple[str | None, int | None, ToolCapability]:
    tool = _version("nvidia-smi", "--version")
    if not tool.available:
        return None, None, tool
    try:
        result = _run(
            [
                tool.path or "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ]
        )
        if result.returncode != 0:
            tool.operational = False
            tool.detail = (result.stderr or result.stdout).strip()
            return None, None, tool
        name, memory_mib = result.stdout.strip().split(",", 1)
        tool.operational = True
        return name.strip(), int(memory_mib.strip()) * 1024 * 1024, tool
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        tool.operational = False
        tool.detail = str(error)
        return None, None, tool


def _sandbox_capability() -> ToolCapability:
    tool = _version("bwrap", "--version")
    if not tool.available:
        return tool
    try:
        result = _run(
            [
                tool.path or "bwrap",
                "--ro-bind",
                "/",
                "/",
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--unshare-user-try",
                "--unshare-pid",
                "--unshare-net",
                "--die-with-parent",
                "/bin/true",
            ]
        )
        tool.operational = result.returncode == 0
        if result.returncode:
            tool.detail = (result.stderr or result.stdout).strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        tool.operational = False
        tool.detail = str(error)
    return tool


def system_profile(data_path: str | Path = ".") -> SystemProfile:
    gpu, gpu_memory, nvidia = _gpu()
    memory = _memory_bytes()
    cpus = os.cpu_count() or 1
    disk = shutil.disk_usage(Path(data_path).resolve()).free
    if gpu and gpu_memory and gpu_memory >= 16 * 1024**3:
        tier = "gpu_large"
    elif gpu:
        tier = "gpu_standard"
    elif memory >= 64 * 1024**3 and cpus >= 16:
        tier = "cpu_large"
    else:
        tier = "cpu_standard"
    project_tool = Path(__file__).resolve().parents[3] / ".tools" / "bin" / "gocryptfs"
    if project_tool.exists():
        os.environ["PATH"] = f"{project_tool.parent}:{os.environ.get('PATH', '')}"
    capabilities = {
        "sandbox": _sandbox_capability(),
        "vault": _version("gocryptfs", "-version"),
        "luks": _version("cryptsetup", "--version"),
        "nvidia": nvidia,
        "signing": ToolCapability(
            available=True,
            operational=True,
            version=f"cryptography {version('cryptography')} · Ed25519",
        ),
        "slurm": _version("sbatch", "--version"),
        "apptainer": _version("apptainer", "--version"),
    }
    return SystemProfile(
        os=platform.platform(),
        kernel=platform.release(),
        compute=ComputeProfile(
            architecture=platform.machine(),
            cpu_model=_cpu_model(),
            logical_cpus=cpus,
            memory_bytes=memory,
            disk_free_bytes=disk,
            gpu=gpu,
            gpu_memory_bytes=gpu_memory,
            recommended_tier=tier,
        ),
        capabilities=capabilities,
        offline_execution_ready=bool(capabilities["sandbox"].operational),
        encrypted_vault_ready=bool(capabilities["vault"].operational),
    )
