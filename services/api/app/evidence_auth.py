from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .schemas import CartEvidence

# The demo issuer's private key stays server-side. By default it is ephemeral; a base64-encoded
# 32-byte seed can be supplied for a stable multi-process demo deployment.
_CONFIGURED_SEED = os.getenv("ACE_DEMO_MERCHANT_PRIVATE_KEY")
_MERCHANT_PRIVATE_KEY = (
    Ed25519PrivateKey.from_private_bytes(
        base64.urlsafe_b64decode(_CONFIGURED_SEED + "=" * (-len(_CONFIGURED_SEED) % 4))
    )
    if _CONFIGURED_SEED
    else Ed25519PrivateKey.generate()
)
_MERCHANT_PUBLIC_KEY = _MERCHANT_PRIVATE_KEY.public_key()

SIGNED_DEMO_EVIDENCE_SOURCES = {
    "SIMULATED_MERCHANT_SIGNED_CART",
    "SIMULATED_PSP_SIGNED_CART",
}


def canonical_cart(cart: CartEvidence) -> bytes:
    return cart.model_dump_json(exclude={"evidence_reference"}, exclude_none=True).encode("utf-8")


def cart_digest(cart: CartEvidence) -> str:
    return hashlib.sha256(canonical_cart(cart)).hexdigest()


def sign_cart_reference(cart: CartEvidence) -> str:
    if cart.evidence_source not in SIGNED_DEMO_EVIDENCE_SOURCES:
        raise ValueError("the demo issuer cannot sign an unsupported evidence source")
    claims = {
        "alg": "EdDSA-demo-merchant",
        "cart_id": cart.cart_id,
        "merchant_id": cart.merchant_id,
        "evidence_source": cart.evidence_source,
        "cart_digest": cart_digest(cart),
        "created_at": cart.created_at.isoformat(),
    }
    payload = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
    signature = _MERCHANT_PRIVATE_KEY.sign(payload)
    return ".".join(
        [
            base64.urlsafe_b64encode(payload).decode().rstrip("="),
            base64.urlsafe_b64encode(signature).decode().rstrip("="),
        ]
    )


def issue_signed_cart(cart: CartEvidence) -> CartEvidence:
    return cart.model_copy(update={"evidence_reference": sign_cart_reference(cart)})


def verify_cart_reference(cart: CartEvidence) -> bool:
    if cart.evidence_source not in SIGNED_DEMO_EVIDENCE_SOURCES:
        return False
    try:
        payload_part, signature_part = cart.evidence_reference.split(".", maxsplit=1)
        payload = base64.urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4))
        signature = base64.urlsafe_b64decode(signature_part + "=" * (-len(signature_part) % 4))
        _MERCHANT_PUBLIC_KEY.verify(signature, payload)
        claims = json.loads(payload)
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
    except Exception:
        return False
    return bool(
        claims.get("alg") == "EdDSA-demo-merchant"
        and claims.get("cart_id") == cart.cart_id
        and claims.get("merchant_id") == cart.merchant_id
        and claims.get("evidence_source") == cart.evidence_source
        and claims.get("created_at") == cart.created_at.isoformat()
        and claims.get("cart_digest") == cart_digest(cart)
    )
