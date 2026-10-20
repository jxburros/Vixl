"""Sign the update manifest with the release key, or make a new key pair. Standard library only.

    python distribution/sign_manifest.py release/vixl-update.json   # key from VIXL_UPDATE_SIGNING_KEY
    python distribution/sign_manifest.py --generate                 # offline, on the owner's machine

The signature goes to `<manifest>.sig` as 128 hex characters: Ed25519 over the manifest's exact bytes. Signing
refuses a key whose public half is not in updater_sign.TRUSTED_KEYS, so a release can never carry a signature
that installed launchers would reject.
"""

import argparse
import os
from pathlib import Path
import re
import secrets
import sys

# Appended, not prepended: src/vixl has modules (selectors.py) that would shadow the standard library.
sys.path.append(str(Path(__file__).resolve().parents[1] / "src" / "vixl"))
import updater_sign  # noqa: E402

ENVIRONMENT = "VIXL_UPDATE_SIGNING_KEY"


def seed_from(text):
    text = (text or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise SystemExit(f"{ENVIRONMENT} must hold the 32-byte Ed25519 secret key as 64 hex characters")
    return bytes.fromhex(text)


def sign_file(manifest, seed, keys=None):
    keys = updater_sign.TRUSTED_KEYS if keys is None else keys
    public = updater_sign.public_key(seed).hex()
    if public not in keys:
        raise SystemExit(
            f"The signing key's public key {public} is not in updater_sign.TRUSTED_KEYS; "
            "add it there in a reviewed release first (docs/reference/releases.md, Update signing)"
        )
    manifest = Path(manifest)
    data = manifest.read_bytes()
    signature = (updater_sign.sign(seed, data).hex() + "\n").encode("ascii")
    if not updater_sign.trusted(data, signature, keys):
        raise SystemExit("The new signature does not verify; nothing was written")
    target = manifest.with_name(manifest.name + ".sig")
    target.write_bytes(signature)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", nargs="?", help="path of vixl-update.json")
    parser.add_argument("--generate", action="store_true", help="print a new secret key and its public key")
    args = parser.parse_args(argv)
    if args.generate:
        seed = secrets.token_bytes(32)
        print(f"secret (store only as the {ENVIRONMENT} secret of the release environment, or offline):")
        print(seed.hex())
        print("public (add to TRUSTED_KEYS in src/vixl/updater_sign.py):")
        print(updater_sign.public_key(seed).hex())
        return 0
    if not args.manifest:
        parser.error("name the manifest to sign, or pass --generate")
    print(sign_file(args.manifest, seed_from(os.environ.get(ENVIRONMENT))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
