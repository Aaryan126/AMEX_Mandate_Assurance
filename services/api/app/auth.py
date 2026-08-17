from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .schemas import MandateProposal

# A deterministic demo seed makes local scenarios reproducible. It is not a production secret.
_DEMO_SEED = hashlib.sha256(b"ace-mandate-assurance-demo-signing-key-v1").digest()
_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(_DEMO_SEED)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()


def canonical_proposal(proposal: MandateProposal) -> bytes:
    return proposal.model_dump_json(exclude_none=True).encode("utf-8")


def proposal_digest(proposal: MandateProposal) -> str:
    return hashlib.sha256(canonical_proposal(proposal)).hexdigest()


def sign_proposal(proposal: MandateProposal, authenticated_at: datetime) -> str:
    claims = {
        "alg": "EdDSA-demo",
        "principal_id": proposal.principal_id,
        "agent_id": proposal.agent_id,
        "mandate_id": proposal.mandate_id,
        "mandate_version": proposal.mandate_version,
        "mandate_digest": proposal_digest(proposal),
        "authenticated_at": authenticated_at.astimezone(UTC).isoformat(),
        "expires_at": proposal.expires_at.astimezone(UTC).isoformat(),
    }
    payload = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
    signature = _PRIVATE_KEY.sign(payload)
    return ".".join(
        [
            base64.urlsafe_b64encode(payload).decode().rstrip("="),
            base64.urlsafe_b64encode(signature).decode().rstrip("="),
        ]
    )


def verify_reference(reference: str, proposal: MandateProposal) -> bool:
    try:
        payload_part, signature_part = reference.split(".", maxsplit=1)
        payload = base64.urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4))
        signature = base64.urlsafe_b64decode(signature_part + "=" * (-len(signature_part) % 4))
        _PUBLIC_KEY.verify(signature, payload)
        claims = json.loads(payload)
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
    except Exception:
        return False
    return bool(
        claims.get("mandate_id") == proposal.mandate_id
        and claims.get("mandate_version") == proposal.mandate_version
        and claims.get("principal_id") == proposal.principal_id
        and claims.get("agent_id") == proposal.agent_id
        and claims.get("mandate_digest") == proposal_digest(proposal)
    )

