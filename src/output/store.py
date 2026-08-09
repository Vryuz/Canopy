"""Attestation store — the difference between a demo and a product.

A verification is only worth something if a third party can pull it up later and check it.
This persists each attestation to disk under its content hash and hands back a short id that
becomes a shareable, re-verifiable URL (`/a/{id}`). The id *is* the first 12 hex of the
content hash, so the address itself is a commitment: change the body and the id no longer
matches.

Disk, not a database, on purpose — the store is a thin interface (`save`/`load`), so swapping
in Postgres/S3 later is a one-file change, not a rewrite.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.output.attestation import Attestation

STORE_DIR = Path(__file__).resolve().parents[2] / "data" / "attestations"

# Short, URL-friendly, and still collision-safe at our scale (12 hex = 48 bits).
ID_LEN = 12


def attestation_id(att: Attestation) -> str:
    return att.content_hash[:ID_LEN]


def save(att: Attestation) -> str:
    """Persist an attestation, returning its shareable id. Idempotent: the same verification
    hashes to the same id and overwrites identically."""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    att_id = attestation_id(att)
    (STORE_DIR / f"{att_id}.json").write_text(att.model_dump_json(indent=2), encoding="utf-8")
    return att_id


def load(att_id: str) -> Attestation | None:
    # Guard against path traversal — the id must be bare hex, never a path.
    if not att_id.isalnum():
        return None
    path = STORE_DIR / f"{att_id}.json"
    if not path.exists():
        return None
    try:
        return Attestation(**json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None
