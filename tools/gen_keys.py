"""Generate Ed25519 keypair for signing release manifests.

Usage:
    python tools/gen_keys.py [output_dir]

Outputs:
    <out>/manifest_priv.pem  (KEEP SECRET — never commit)
    <out>/manifest_pub.pem   (commit to repo + paste hex into update_keys.py)

The hex-encoded public key is also printed to stdout. Paste it into
update_keys.PUBLIC_KEY_HEX so the client can verify signatures.
"""
from __future__ import annotations

import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/keys")
    out_dir.mkdir(parents=True, exist_ok=True)

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()

    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub_raw = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    priv_path = out_dir / "manifest_priv.pem"
    pub_path = out_dir / "manifest_pub.pem"
    priv_path.write_bytes(priv_pem)
    pub_path.write_bytes(pub_pem)

    print(f"[gen_keys] private key: {priv_path}  (KEEP SECRET)")
    print(f"[gen_keys] public  key: {pub_path}")
    print()
    print(f"PUBLIC_KEY_HEX = \"{pub_raw.hex()}\"")
    print()
    print("Paste the line above into update_keys.py (PUBLIC_KEY_HEX constant).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
