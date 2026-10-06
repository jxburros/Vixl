"""Bounded HTTPS downloads for explicit URL imports (images, fonts).

Policy: HTTPS only, no credentials in the URL, at most ``MAX_REDIRECTS`` redirects (each hop is
validated again), a streamed byte cap, a 30 s timeout per network step and 120 s in all. Every
address a host resolves to must be public: private, loopback, link-local, shared (CGNAT),
multicast, reserved and unspecified addresses are refused, including IPv4 addresses embedded in IPv6 (mapped, compatible, NAT64,
6to4, Teredo). Without a proxy the connection goes to the address that was checked (the host
name is kept for the Host header, SNI and certificate verification), so a second DNS answer
cannot redirect it. With an environment HTTP(S) proxy the proxy resolves and connects; the check
then runs on Vixl's own resolution when there is one, and the proxy's policy is the final boundary.

``VIXL_ALLOW_PRIVATE_FETCH=1`` disables the address check (intranet hosts, local test servers);
the HTTPS, credential, redirect and size rules still apply.
"""

from datetime import datetime, timezone
import hashlib
import ipaddress
import os
import socket
import time
import urllib.request
from urllib.parse import urljoin, urlsplit

import httpx

from .errors import VixlError, require

MAX_REDIRECTS = 5
TIMEOUT = 30
TOTAL_TIMEOUT = 120
ALLOW_PRIVATE_ENV = "VIXL_ALLOW_PRIVATE_FETCH"
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def resolve(host, port):
    """All addresses ``host`` resolves to. Tests replace this to stay offline."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise VixlError("fetch_failed", f"Cannot resolve host {host!r}") from exc
    return list(dict.fromkeys(info[4][0].split("%", 1)[0] for info in infos))


def _embedded_ipv4(ip):
    if ip.version != 6:
        return None
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip.sixtofour:
        return ip.sixtofour
    if ip.teredo:
        return ip.teredo[1]
    if ip in _NAT64 or int(ip) >> 32 == 0:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def public_address(address):
    """True when ``address`` is a globally routable unicast address."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    embedded = _embedded_ipv4(ip)
    if embedded is not None and not public_address(str(embedded)):
        return False
    return ip.is_global and not ip.is_multicast and not ip.is_unspecified


def _private_allowed():
    return os.environ.get(ALLOW_PRIVATE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _proxied(host):
    proxies = urllib.request.getproxies_environment()
    if not (proxies.get("https") or proxies.get("all")):
        return False
    return not urllib.request.proxy_bypass_environment(host, proxies)


def check_url(url, label="URL"):
    """Validate scheme and credentials; return the parsed URL."""
    require(isinstance(url, str) and url.strip(), f"{label} must be a non-empty string", field="url")
    parts = urlsplit(url.strip())
    require(parts.scheme.lower() == "https", f"{label} downloads require HTTPS", "unsafe_url", field="url")
    require(parts.username is None and parts.password is None, "URLs cannot contain credentials",
            "unsafe_url", field="url")
    require(parts.hostname, f"{label} has no host", "unsafe_url", field="url")
    try:
        parts.port
    except ValueError as exc:
        raise VixlError("unsafe_url", f"{label} has an invalid port", field="url") from exc
    return parts


def _target(parts, proxied, label):
    """Check the host's addresses; return the address to connect to (None: connect by name)."""
    host, port = parts.hostname, parts.port or 443
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    allow = _private_allowed()
    if literal is not None:
        addresses = [str(literal)]
    else:
        try:
            addresses = resolve(host, port)
        except VixlError:
            if proxied:
                return None  # Only the proxy can resolve this name.
            raise
        require(addresses, f"Cannot resolve host {host!r}", "fetch_failed", field="url")
    if not allow:
        blocked = [a for a in addresses if not public_address(a)]
        if blocked:
            raise VixlError("unsafe_url", f"{label} host {host!r} resolves to a non-public address ({blocked[0]}); "
                            f"set {ALLOW_PRIVATE_ENV}=1 to allow intranet hosts", field="url")
    return None if proxied else addresses[0]


def _pinned_request(client, parts, address, accept):
    host = parts.hostname
    netloc = f"[{address}]" if ":" in address else address
    if parts.port:
        netloc += f":{parts.port}"
    host_header = f"[{host}]" if ":" in host else host
    if parts.port:
        host_header += f":{parts.port}"
    url = parts._replace(netloc=netloc).geturl()
    headers = {"Host": host_header, "Accept": accept, "User-Agent": "vixl"}
    return client.build_request("GET", url, headers=headers, extensions={"sni_hostname": host})


def fetch_bounded(url, limit, *, accept="*/*", label="URL"):
    """Download ``url`` under the network policy above. Returns ``(data, info)`` where info holds
    the final ``url``, ``bytes``, ``sha256``, ``fetched_at`` and, after redirects, ``requested_url``."""
    current = url.strip() if isinstance(url, str) else url
    deadline = time.monotonic() + TOTAL_TIMEOUT
    for hop in range(MAX_REDIRECTS + 1):
        parts = check_url(current, label)
        proxied = _proxied(parts.hostname)
        address = _target(parts, proxied, label)
        active = httpx.Client(timeout=TIMEOUT, follow_redirects=False, trust_env=proxied)
        try:
            if address is None:
                request = active.build_request("GET", current, headers={"Accept": accept, "User-Agent": "vixl"})
            else:
                request = _pinned_request(active, parts, address, accept)
            response = active.send(request, stream=True)
            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    require(location, f"{label} redirect has no Location", "fetch_failed", field="url")
                    current = urljoin(current, location)
                    continue
                require(response.status_code == 200, f"{label} download returned HTTP {response.status_code}",
                        "fetch_failed", field="url")
                declared = response.headers.get("content-length", "")
                require(not declared.isdigit() or int(declared) <= limit,
                        f"{label} download exceeds the {limit}-byte limit", "resource_limit", field="url")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    require(time.monotonic() < deadline, f"{label} download took longer than {TOTAL_TIMEOUT} s",
                            "fetch_failed", field="url")
                    require(len(data) <= limit, f"{label} download exceeds the {limit}-byte limit",
                            "resource_limit", field="url")
            finally:
                response.close()
        except httpx.HTTPError as exc:
            raise VixlError("fetch_failed", f"{label} download failed ({type(exc).__name__})", field="url") from exc
        finally:
            active.close()
        data = bytes(data)
        info = {"url": current, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}
        if hop:
            info["requested_url"] = url.strip()
        return data, info
    raise VixlError("fetch_failed", f"{label} redirected more than {MAX_REDIRECTS} times", field="url")
