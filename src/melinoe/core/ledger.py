from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class LedgerEvent(BaseModel):
    sequence: int
    timestamp: str
    action: str
    actor: str
    details: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str
    event_hash: str


class LedgerVerification(BaseModel):
    valid: bool
    event_count: int
    head_hash: str
    error: str | None = None


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


class AuditLedger:
    """Append-only, hash-chained local event ledger.

    The chain makes accidental or retrospective edits detectable. It is not a digital
    signature and does not protect against an attacker who can replace the whole ledger.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(
        self,
        action: str,
        *,
        actor: str = "local-user",
        details: dict[str, Any] | None = None,
    ) -> LedgerEvent:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            events = [json.loads(line) for line in handle if line.strip()]
            previous_hash = events[-1]["event_hash"] if events else "0" * 64
            payload = {
                "sequence": len(events) + 1,
                "timestamp": datetime.now(UTC).isoformat(),
                "action": action,
                "actor": actor,
                "details": details or {},
                "previous_hash": previous_hash,
            }
            event = LedgerEvent(
                **payload,
                event_hash=hashlib.sha256(_canonical(payload)).hexdigest(),
            )
            handle.seek(0, os.SEEK_END)
            handle.write(event.model_dump_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle, fcntl.LOCK_UN)
        return event

    def verify(self) -> LedgerVerification:
        if not self.path.exists():
            return LedgerVerification(valid=True, event_count=0, head_hash="0" * 64)
        previous_hash = "0" * 64
        count = 0
        try:
            for count, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
                raw = json.loads(line)
                event = LedgerEvent.model_validate(raw)
                payload = event.model_dump(exclude={"event_hash"})
                expected = hashlib.sha256(_canonical(payload)).hexdigest()
                if event.sequence != count:
                    raise ValueError(f"event {count} has sequence {event.sequence}")
                if event.previous_hash != previous_hash:
                    raise ValueError(f"event {count} breaks the previous-hash chain")
                if event.event_hash != expected:
                    raise ValueError(f"event {count} content hash does not match")
                previous_hash = event.event_hash
        except (ValueError, json.JSONDecodeError) as error:
            return LedgerVerification(
                valid=False,
                event_count=count,
                head_hash=previous_hash,
                error=str(error),
            )
        return LedgerVerification(valid=True, event_count=count, head_hash=previous_hash)
