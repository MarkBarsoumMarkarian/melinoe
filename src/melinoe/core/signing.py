from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel


class SignatureEnvelope(BaseModel):
    format: str = "melinoe-signature/1.0"
    algorithm: str = "Ed25519"
    key_id: str
    payload_sha256: str
    public_key: str
    signature: str


class SignatureVerification(BaseModel):
    valid: bool
    key_id: str
    payload_sha256: str
    error: str | None = None


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def generate_signing_key(
    private_path: str | Path,
    public_path: str | Path,
    passphrase: str,
) -> str:
    if len(passphrase) < 12:
        raise ValueError("Signing-key passphrases must contain at least 12 characters")
    private_file = Path(private_path)
    public_file = Path(public_path)
    if private_file.exists() or public_file.exists():
        raise FileExistsError("refusing to overwrite an existing signing key")
    private_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    public_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(passphrase.encode("utf-8")),
    )
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    private_file.write_bytes(private_bytes)
    os.chmod(private_file, 0o600)
    public_file.write_text(base64.b64encode(public_bytes).decode("ascii") + "\n", encoding="utf-8")
    os.chmod(public_file, 0o644)
    return hashlib.sha256(public_bytes).hexdigest()[:16]


def _load_private_key(path: str | Path, passphrase: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(
        Path(path).read_bytes(),
        password=passphrase.encode("utf-8"),
    )
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("the supplied key is not an Ed25519 private key")
    return key


def sign_payload(
    payload: dict[str, Any],
    private_path: str | Path,
    passphrase: str,
) -> SignatureEnvelope:
    private_key = _load_private_key(private_path, passphrase)
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    content = canonical_json(payload)
    return SignatureEnvelope(
        key_id=hashlib.sha256(public_bytes).hexdigest()[:16],
        payload_sha256=hashlib.sha256(content).hexdigest(),
        public_key=base64.b64encode(public_bytes).decode("ascii"),
        signature=base64.b64encode(private_key.sign(content)).decode("ascii"),
    )


def verify_payload(
    payload: dict[str, Any],
    envelope: SignatureEnvelope | dict[str, Any],
) -> SignatureVerification:
    signature = SignatureEnvelope.model_validate(envelope)
    content = canonical_json(payload)
    digest = hashlib.sha256(content).hexdigest()
    if digest != signature.payload_sha256:
        return SignatureVerification(
            valid=False,
            key_id=signature.key_id,
            payload_sha256=digest,
            error="payload digest does not match the signed digest",
        )
    try:
        public_bytes = base64.b64decode(signature.public_key, validate=True)
        expected_key_id = hashlib.sha256(public_bytes).hexdigest()[:16]
        if expected_key_id != signature.key_id:
            raise ValueError("public key does not match key identifier")
        public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
        public_key.verify(base64.b64decode(signature.signature, validate=True), content)
    except (InvalidSignature, ValueError) as error:
        return SignatureVerification(
            valid=False,
            key_id=signature.key_id,
            payload_sha256=digest,
            error=str(error) or "signature verification failed",
        )
    return SignatureVerification(valid=True, key_id=signature.key_id, payload_sha256=digest)
