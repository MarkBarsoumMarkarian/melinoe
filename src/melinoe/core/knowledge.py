from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, Field

from melinoe.core.signing import SignatureEnvelope, sign_payload, verify_payload


class KnowledgeSource(BaseModel):
    name: str
    version: str
    url: str
    license: str
    retrieved_at: datetime


class KnowledgeFile(BaseModel):
    path: str
    size_bytes: int
    sha256: str
    media_type: str | None = None


class KnowledgeManifest(BaseModel):
    format: str = "melinoe-knowledge-pack/1.0"
    pack_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    version: str
    title: str
    description: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sources: list[KnowledgeSource]
    files: list[KnowledgeFile] = Field(default_factory=list)


class KnowledgeVerification(BaseModel):
    valid: bool
    pack_id: str | None = None
    version: str | None = None
    file_count: int = 0
    package_sha256: str
    signer_key_id: str | None = None
    errors: list[str] = Field(default_factory=list)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and path.parts[0] != ""


def build_knowledge_pack(
    source_directory: str | Path,
    manifest: KnowledgeManifest,
    output: str | Path,
    private_key: str | Path,
    passphrase: str,
) -> Path:
    source = Path(source_directory).resolve()
    if not source.is_dir():
        raise ValueError("knowledge source directory does not exist")
    records: list[KnowledgeFile] = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"knowledge packs cannot contain symlinks: {path}")
        if path.is_file():
            relative = path.relative_to(source).as_posix()
            records.append(
                KnowledgeFile(
                    path=f"data/{relative}",
                    size_bytes=path.stat().st_size,
                    sha256=_sha256_file(path),
                )
            )
    if not records:
        raise ValueError("knowledge packs must contain at least one data file")
    manifest = manifest.model_copy(update={"files": records})
    payload = manifest.model_dump(mode="json")
    signature = sign_payload(payload, private_key, passphrase)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "knowledge-manifest.json",
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )
        archive.writestr("signature.json", signature.model_dump_json(indent=2) + "\n")
        for record in records:
            relative = PurePosixPath(record.path).relative_to("data")
            archive.write(source / Path(*relative.parts), record.path)
    return output_path


def verify_knowledge_pack(path: str | Path) -> KnowledgeVerification:
    package = Path(path)
    package_hash = _sha256_file(package) if package.is_file() else ""
    errors: list[str] = []
    pack_id = version = key_id = None
    file_count = 0
    try:
        with zipfile.ZipFile(package) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                errors.append("archive contains duplicate member names")
            for info in infos:
                if not _safe_member(info.filename):
                    errors.append(f"unsafe archive path: {info.filename}")
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    errors.append(f"archive contains a symlink: {info.filename}")
            manifest = KnowledgeManifest.model_validate_json(
                archive.read("knowledge-manifest.json")
            )
            signature = SignatureEnvelope.model_validate_json(archive.read("signature.json"))
            pack_id, version, key_id = manifest.pack_id, manifest.version, signature.key_id
            signed = verify_payload(manifest.model_dump(mode="json"), signature)
            if not signed.valid:
                errors.append(signed.error or "signature verification failed")
            declared = {record.path: record for record in manifest.files}
            actual_data = {
                name for name in names if name.startswith("data/") and not name.endswith("/")
            }
            if set(declared) != actual_data:
                errors.append("declared and archived data files differ")
            for member, record in declared.items():
                content = archive.read(member)
                if len(content) != record.size_bytes:
                    errors.append(f"size mismatch: {member}")
                if hashlib.sha256(content).hexdigest() != record.sha256:
                    errors.append(f"checksum mismatch: {member}")
            file_count = len(declared)
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        errors.append(str(error))
    return KnowledgeVerification(
        valid=not errors,
        pack_id=pack_id,
        version=version,
        file_count=file_count,
        package_sha256=package_hash,
        signer_key_id=key_id,
        errors=errors,
    )


def install_knowledge_pack(path: str | Path, registry: str | Path) -> Path:
    verification = verify_knowledge_pack(path)
    if not verification.valid or not verification.pack_id or not verification.version:
        raise ValueError("knowledge pack verification failed: " + "; ".join(verification.errors))
    destination_dir = Path(registry) / verification.pack_id / verification.version
    destination_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
    destination = destination_dir / f"{verification.package_sha256}.mknowledge"
    if destination.exists():
        return destination
    descriptor, temporary = tempfile.mkstemp(prefix=".install-", dir=destination_dir)
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        shutil.copyfile(path, temporary_path)
        if _sha256_file(temporary_path) != verification.package_sha256:
            raise ValueError("knowledge pack changed during installation")
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return destination


def list_knowledge_packs(registry: str | Path) -> list[KnowledgeVerification]:
    root = Path(registry)
    if not root.exists():
        return []
    return [verify_knowledge_pack(path) for path in sorted(root.rglob("*.mknowledge"))]
