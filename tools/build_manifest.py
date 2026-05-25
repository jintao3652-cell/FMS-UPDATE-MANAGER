"""Build a signed manifest for an incremental release.

Usage:
    python tools/build_manifest.py <dist_dir> <version> [--privkey path] [--out-dir path]

Default:
    --privkey   tools/keys/manifest_priv.pem   (or env FMS_MANIFEST_PRIVKEY)
    --out-dir   <dist_dir>/..                  (manifest written next to dist)

Outputs:
    <out_dir>/manifest.json
    <out_dir>/manifest.json.sig

Manifest schema:
    {
        "version": "1.0.7",
        "generated_at": "2026-05-25T...Z",
        "files": [
            {"path": "FMS_UPDATE_MANAGER.exe", "sha256": "...", "size": 12345},
            ...
        ]
    }
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            buf = fh.read(CHUNK)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def build_files(dist_dir: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted(dist_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(dist_dir).as_posix()
        if rel == "portable.flag":
            continue
        out.append({
            "path": rel,
            "sha256": sha256_file(p),
            "size": p.stat().st_size,
        })
    return out


def load_privkey(path: Path) -> Ed25519PrivateKey:
    data = path.read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit(f"[build_manifest] not an Ed25519 private key: {path}")
    return key


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dist_dir", type=Path)
    ap.add_argument("version")
    ap.add_argument("--privkey", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args()

    dist_dir: Path = args.dist_dir.resolve()
    if not dist_dir.is_dir():
        print(f"[build_manifest] not a directory: {dist_dir}", file=sys.stderr)
        return 1

    priv_path = args.privkey or Path(os.environ.get("FMS_MANIFEST_PRIVKEY", "tools/keys/manifest_priv.pem"))
    if not priv_path.exists():
        print(f"[build_manifest] private key not found: {priv_path}", file=sys.stderr)
        return 1

    out_dir: Path = (args.out_dir or dist_dir.parent).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[build_manifest] hashing files under {dist_dir} ...")
    files = build_files(dist_dir)
    manifest = {
        "version": args.version,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")

    priv = load_privkey(priv_path)
    sig = priv.sign(manifest_bytes)

    manifest_path = out_dir / "manifest.json"
    sig_path = out_dir / "manifest.json.sig"
    manifest_path.write_bytes(manifest_bytes)
    sig_path.write_bytes(sig)

    print(f"[build_manifest] {len(files)} files, total {sum(f['size'] for f in files):,} bytes")
    print(f"[build_manifest] manifest: {manifest_path}")
    print(f"[build_manifest] sig     : {sig_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
