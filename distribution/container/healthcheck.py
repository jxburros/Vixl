"""Container HEALTHCHECK: GET /host/health with the host's own bearer token.

/host/health needs the token like every host route, so this reads it the way ``vixl host`` does:
``VIXL_HOST_TOKEN_FILE`` (a file, wins) or ``VIXL_HOST_TOKEN``. Exit 0 when the host answers ``ok: true``.
"""

import json
import os
import sys
import urllib.request

PORT = os.environ.get("VIXL_HOST_PORT", "8767")


def token():
    path = os.environ.get("VIXL_HOST_TOKEN_FILE", "").strip()
    if path:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    return os.environ.get("VIXL_HOST_TOKEN", "").strip()


def main():
    request = urllib.request.Request(f"http://127.0.0.1:{PORT}/host/health",
                                     headers={"Authorization": f"Bearer {token()}"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - a fixed loopback URL
            return 0 if json.load(response).get("ok") is True else 1
    except (OSError, ValueError):
        return 1


if __name__ == "__main__":
    sys.exit(main())
