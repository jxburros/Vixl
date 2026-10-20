"""Ed25519 signatures for update manifests (RFC 8032). Standard library only.

The stable launcher freezes this module beside updater.py, outside the vixl package, so it must not import the
engine. Verification is plain integer arithmetic; it handles only public data, so it need not be constant-time.
`sign` exists for the release workflow and the tests.
"""

import hashlib
import re

# Public keys (32 bytes, hex) that may sign vixl-update.json: the primary key held in the protected `release`
# environment, then an offline backup for rotation. A build with no key refuses every update
# (docs/reference/releases.md, "Update signing").
TRUSTED_KEYS = ()

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)
_IDENTITY = (0, 1, 1, 0)


def _add(a, b):
    """Extended twisted Edwards coordinates (X, Y, Z, T), x = X/Z, y = Y/Z, xy = T/Z."""
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    e = (y1 - x1) * (y2 - x2) % _P
    f = (y1 + x1) * (y2 + x2) % _P
    g = t1 * 2 * _D * t2 % _P
    h = z1 * 2 * z2 % _P
    e, f, g, h = f - e, h - g, h + g, f + e
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _multiply(scalar, point):
    result = _IDENTITY
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _equal(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P:
        return None
    return _P - x if (x & 1) != sign else x


def _decode(data):
    if len(data) != 32:
        return None
    y = int.from_bytes(data, "little")
    x = _recover_x(y & ((1 << 255) - 1), y >> 255)
    if x is None:
        return None
    y &= (1 << 255) - 1
    return (x, y, 1, x * y % _P)


def _encode(point):
    x, y, z, _ = point
    inverse = pow(z, _P - 2, _P)
    x, y = x * inverse % _P, y * inverse % _P
    return (y | (x & 1) << 255).to_bytes(32, "little")


_BASE_Y = 4 * pow(5, _P - 2, _P) % _P
_BASE_X = _recover_x(_BASE_Y, 0)
_BASE = (_BASE_X, _BASE_Y, 1, _BASE_X * _BASE_Y % _P)


def _hash(*parts):
    return int.from_bytes(hashlib.sha512(b"".join(parts)).digest(), "little")


def verify(public, message, signature):
    """True when `signature` (64 bytes) is a valid Ed25519 signature of `message` by `public` (32 bytes)."""
    if not (isinstance(public, bytes) and isinstance(signature, bytes)) or len(public) != 32 or len(signature) != 64:
        return False
    a = _decode(public)
    r = _decode(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if a is None or r is None or s >= _L:
        return False
    k = _hash(signature[:32], public, message) % _L
    return _equal(_multiply(s, _BASE), _add(r, _multiply(k, a)))


def _secret(seed):
    if not isinstance(seed, bytes) or len(seed) != 32:
        raise ValueError("An Ed25519 secret key is 32 bytes")
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], "little") & ((1 << 254) - 8) | (1 << 254)
    return scalar, digest[32:]


def public_key(seed):
    return _encode(_multiply(_secret(seed)[0], _BASE))


def sign(seed, message):
    scalar, prefix = _secret(seed)
    public = _encode(_multiply(scalar, _BASE))
    r = _hash(prefix, message) % _L
    encoded = _encode(_multiply(r, _BASE))
    return encoded + ((r + _hash(encoded, public, message) * scalar) % _L).to_bytes(32, "little")


def parse_signature(data):
    """The 64 signature bytes from a .sig file (128 hex characters, optional trailing newline), or None."""
    try:
        text = data.decode("ascii").strip()
    except (AttributeError, UnicodeDecodeError):
        return None
    return bytes.fromhex(text) if re.fullmatch(r"[0-9a-f]{128}", text) else None


def trusted(message, signature, keys=None):
    """True when any trusted key verifies `signature`, the raw bytes of a .sig file, over `message`."""
    raw = parse_signature(signature)
    keys = TRUSTED_KEYS if keys is None else keys
    return raw is not None and any(verify(bytes.fromhex(key), message, raw) for key in keys)
