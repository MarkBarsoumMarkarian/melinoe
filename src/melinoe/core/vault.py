from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from melinoe.core.ledger import AuditLedger


class VaultStatus(BaseModel):
    root: str
    initialized: bool
    mounted: bool
    engine_available: bool
    engine_version: str | None = None
    cipher_directory: str
    mount_directory: str


def _engine() -> str | None:
    packaged = Path(__file__).resolve().parents[3] / ".tools" / "bin" / "gocryptfs"
    return str(packaged) if packaged.is_file() else shutil.which("gocryptfs")


def _paths(root: str | Path) -> tuple[Path, Path, Path]:
    base = Path(root).resolve()
    return base, base / "cipher", base / "workspace"


def _mounted(path: Path) -> bool:
    target = str(path)
    try:
        for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if len(fields) > 4 and fields[4].replace("\\040", " ") == target:
                return True
    except OSError:
        pass
    return False


def status(root: str | Path) -> VaultStatus:
    base, cipher, mount = _paths(root)
    binary = _engine()
    version = None
    if binary:
        result = subprocess.run(
            [binary, "-version"], capture_output=True, text=True, check=False, timeout=3
        )
        version = (result.stdout or result.stderr).strip().splitlines()[0]
    return VaultStatus(
        root=str(base),
        initialized=(cipher / "gocryptfs.conf").is_file(),
        mounted=_mounted(mount),
        engine_available=binary is not None,
        engine_version=version,
        cipher_directory=str(cipher),
        mount_directory=str(mount),
    )


def create(root: str | Path, password: str) -> VaultStatus:
    if len(password) < 12:
        raise ValueError("Project Vault passphrases must contain at least 12 characters")
    binary = _engine()
    if not binary:
        raise RuntimeError("gocryptfs is unavailable; run scripts/install-vault-engine.sh")
    base, cipher, mount = _paths(root)
    if (cipher / "gocryptfs.conf").exists():
        raise FileExistsError(f"a Project Vault already exists at {base}")
    cipher.mkdir(parents=True, mode=0o700)
    mount.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(base, 0o700)
    result = subprocess.run(
        [binary, "-init", str(cipher)],
        input=f"{password}\n{password}\n",
        stdout=None,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Project Vault initialization failed")
    metadata = {
        "format": "melinoe-project-vault/1.0",
        "created_at": datetime.now(UTC).isoformat(),
        "engine": "gocryptfs",
    }
    metadata_path = base / "vault.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    os.chmod(metadata_path, 0o600)
    AuditLedger(base / "ledger.jsonl").append("vault.created", details={"engine": "gocryptfs"})
    return status(base)


def open_vault(root: str | Path, password: str) -> VaultStatus:
    binary = _engine()
    if not binary:
        raise RuntimeError("gocryptfs is unavailable; run scripts/install-vault-engine.sh")
    base, cipher, mount = _paths(root)
    if _mounted(mount):
        return status(base)
    if not (cipher / "gocryptfs.conf").is_file():
        raise FileNotFoundError(f"no Project Vault exists at {base}")
    mount.mkdir(parents=True, exist_ok=True, mode=0o700)
    result = subprocess.run(
        [binary, "-q", "-nosyslog", str(cipher), str(mount)],
        input=f"{password}\n",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode:
        raise RuntimeError("Project Vault unlock failed")
    AuditLedger(base / "ledger.jsonl").append("vault.opened")
    return status(base)


def close_vault(root: str | Path) -> VaultStatus:
    base, _, mount = _paths(root)
    if not _mounted(mount):
        return status(base)
    unmount = shutil.which("fusermount3") or shutil.which("fusermount")
    if not unmount:
        raise RuntimeError("FUSE unmount helper is unavailable")
    result = subprocess.run([unmount, "-u", str(mount)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Project Vault could not be locked")
    AuditLedger(base / "ledger.jsonl").append("vault.closed")
    return status(base)
