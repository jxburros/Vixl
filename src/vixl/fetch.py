"""Bounded HTTPS downloads for explicit URL imports (images, fonts), and the network switch.

Policy: HTTPS only, no credentials in the URL, at most ``MAX_REDIRECTS`` redirects (each hop is
validated again), a streamed byte cap, a 30 s timeout per network step and 120 s in all. Internal
names (``localhost``, ``*.local``, ``*.internal``, ``*.svc``, names without a dot) are refused
before resolution. Every address a host resolves to must be public: private, loopback, link-local,
shared (CGNAT), multicast, reserved, site-local, SRv6 and unspecified addresses are refused,
including IPv4 addresses embedded in IPv6 (mapped, translated, compatible, NAT64, 6to4, Teredo).
Without a proxy the connection goes to the address that was checked (the host name is kept for the
Host header, SNI and certificate verification), so a second DNS answer cannot redirect it. With an
environment HTTP(S) proxy the proxy resolves and connects; Vixl still resolves the name first and
checks the answer, and refuses a name it cannot resolve unless ``VIXL_PROXY_RESOLVES=1`` says that
only the proxy can.

``VIXL_ALLOW_PRIVATE_FETCH=1`` disables the name and address checks (intranet hosts, local test
servers); the HTTPS, credential, redirect and size rules still apply. ``VIXL_FETCH_HOSTS`` (a comma
list of hosts and ``*.suffix`` patterns) limits explicit URL imports to those hosts.
``VIXL_OFFLINE=1`` turns off every network access Vixl makes on its own (``network_allowed``).

``post_bounded`` sends a small POST (completion webhooks) under the same name, address and offline rules, never
follows a redirect, and accepts plain HTTP only to a loopback address when the caller allows it.
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
OFFLINE_ENV = "VIXL_OFFLINE"
FETCH_HOSTS_ENV = "VIXL_FETCH_HOSTS"
PROXY_RESOLVES_ENV = "VIXL_PROXY_RESOLVES"
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_TRANSLATED = ipaddress.ip_network("::ffff:0:0:0/96")  # IPv4-translated (RFC 2765); ``is_global`` misses it.
# Ranges ``is_global`` reports as global on some Python versions: deprecated site-local, SRv6 SIDs
# (RFC 9602) and the documentation ranges.
_DENY6 = (ipaddress.ip_network("fec0::/10"), ipaddress.ip_network("5f00::/16"),
          ipaddress.ip_network("2001:db8::/32"), ipaddress.ip_network("3fff::/20"))
INTERNAL_SUFFIXES = (".localhost", ".local", ".internal", ".svc")


def _flag(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def offline():
    """True when ``VIXL_OFFLINE`` (or ``--offline`` on ``vixl mcp``, ``serve`` and ``view``) is set."""
    return _flag(OFFLINE_ENV)


# URL prefixes offline mode still lets through: the AI gateway ``vixl host --provider studio`` names, and nothing else.
OFFLINE_EXCEPTIONS = set()


def allow_offline(prefix):
    """Let ``network_allowed(purpose, url)`` pass for URLs under ``prefix`` (scheme, host, port and path) while offline."""
    OFFLINE_EXCEPTIONS.add(prefix.rstrip("/") + "/")


def disallow_offline(prefix):
    OFFLINE_EXCEPTIONS.discard(prefix.rstrip("/") + "/")


def offline_exception(url):
    return isinstance(url, str) and any(url.startswith(prefix) for prefix in OFFLINE_EXCEPTIONS)


def network_allowed(purpose, url=None):
    """Refuse with ``network_disabled`` when offline mode is on; every network entry point calls this first. A ``url``
    under a prefix ``allow_offline`` registered passes."""
    if offline() and not offline_exception(url):
        raise VixlError("network_disabled", f"{purpose} needs the network, and {OFFLINE_ENV}=1 turns network "
                        "access off", suggestions=[f"Unset {OFFLINE_ENV} (or drop --offline) to allow it",
                                                   "Use a local file or the font cache instead"])


def fetch_hosts():
    """The ``VIXL_FETCH_HOSTS`` patterns (lower case), or None when every public host is allowed."""
    patterns = [item.strip().lower().rstrip(".") for item in os.environ.get(FETCH_HOSTS_ENV, "").split(",")]
    return [item for item in patterns if item] or None


def host_listed(host, patterns):
    """True when ``host`` equals a pattern, or is a subdomain of a ``*.suffix`` pattern."""
    host = host.lower().rstrip(".")
    return any(host == p or (p.startswith("*.") and host.endswith(p[1:])) for p in patterns)


def internal_name(host):
    """True for names that only make sense inside a network: localhost, mDNS, cluster and dotless names."""
    host = host.lower().rstrip(".")
    return host == "localhost" or "." not in host or host.endswith(INTERNAL_SUFFIXES)


def policy():
    """The network policy in force, as services report it (``GET /limits``)."""
    return {"offline": offline(), "fetch_hosts": fetch_hosts(), "private_addresses": _private_allowed(),
            "proxy_resolves": _flag(PROXY_RESOLVES_ENV),
            "configure": {"offline": OFFLINE_ENV, "fetch_hosts": FETCH_HOSTS_ENV,
                          "private_addresses": ALLOW_PRIVATE_ENV, "proxy_resolves": PROXY_RESOLVES_ENV}}


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
    if ip in _NAT64 or ip in _TRANSLATED or int(ip) >> 32 == 0:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def public_address(address):
    """True when ``address`` is a globally routable unicast address."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip.version == 6 and any(ip in network for network in _DENY6):
        return False
    embedded = _embedded_ipv4(ip)
    if embedded is not None and not public_address(str(embedded)):
        return False
    return ip.is_global and not ip.is_multicast and not ip.is_unspecified


def _private_allowed():
    return _flag(ALLOW_PRIVATE_ENV)


def _proxied(host):
    proxies = urllib.request.getproxies_environment()
    if not (proxies.get("https") or proxies.get("all")):
        return False
    return not urllib.request.proxy_bypass_environment(host, proxies)


def loopback(host):
    """True for ``localhost`` and loopback address literals."""
    host = (host or "").lower().rstrip(".")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_url(url, label="URL", *, allow_list=True, loopback_http=False):
    """Validate scheme, credentials and (with ``allow_list``) the ``VIXL_FETCH_HOSTS`` list; return the parsed URL.
    ``loopback_http`` also accepts ``http://`` to a loopback host (a receiver on the same machine)."""
    require(isinstance(url, str) and url.strip(), f"{label} must be a non-empty string", field="url")
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    plain = loopback_http and scheme == "http" and loopback(parts.hostname)
    require(scheme == "https" or plain, f"{label} requires HTTPS (plain HTTP only to a loopback address)"
            if loopback_http else f"{label} downloads require HTTPS", "unsafe_url", field="url")
    require(parts.username is None and parts.password is None, "URLs cannot contain credentials",
            "unsafe_url", field="url")
    require(parts.hostname, f"{label} has no host", "unsafe_url", field="url")
    try:
        parts.port
    except ValueError as exc:
        raise VixlError("unsafe_url", f"{label} has an invalid port", field="url") from exc
    patterns = fetch_hosts() if allow_list else None
    if patterns and not host_listed(parts.hostname, patterns):
        raise VixlError("unsafe_url", f"{label} host {parts.hostname!r} is not in {FETCH_HOSTS_ENV}",
                        field="url", allowed=patterns)
    return parts


def _target(parts, proxied, label):
    """Check the host's addresses; return the address to connect to (None: connect by name)."""
    host, port = parts.hostname, parts.port or (80 if parts.scheme.lower() == "http" else 443)
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    allow = _private_allowed()
    if literal is not None:
        addresses = [str(literal)]
    else:
        if not allow and internal_name(host):
            raise VixlError("unsafe_url", f"{label} host {host!r} is an internal name; set {ALLOW_PRIVATE_ENV}=1 "
                            "to allow intranet hosts", field="url")
        try:
            addresses = resolve(host, port)
        except VixlError as exc:
            if proxied and _flag(PROXY_RESOLVES_ENV):
                return None  # Opted in: only the proxy can resolve this name.
            if proxied:
                raise VixlError("fetch_failed", f"Cannot resolve host {host!r}, so its address cannot be checked; "
                                f"set {PROXY_RESOLVES_ENV}=1 if only the proxy can resolve names", field="url") from exc
            raise
        require(addresses, f"Cannot resolve host {host!r}", "fetch_failed", field="url")
    if not allow:
        blocked = [a for a in addresses if not public_address(a)]
        if blocked:
            raise VixlError("unsafe_url", f"{label} host {host!r} resolves to a non-public address ({blocked[0]}); "
                            f"set {ALLOW_PRIVATE_ENV}=1 to allow intranet hosts", field="url")
    return None if proxied else addresses[0]


def _pinned_request(client, parts, address, accept, method="GET", content=None, headers=None):
    host = parts.hostname
    netloc = f"[{address}]" if ":" in address else address
    if parts.port:
        netloc += f":{parts.port}"
    host_header = f"[{host}]" if ":" in host else host
    if parts.port:
        host_header += f":{parts.port}"
    url = parts._replace(netloc=netloc).geturl()
    headers = {**(headers or {}), "Host": host_header, "Accept": accept, "User-Agent": "vixl"}
    return client.build_request(method, url, headers=headers, content=content, extensions={"sni_hostname": host})


def fetch_bounded(url, limit, *, accept="*/*", label="URL", allow_list=True):
    """Download ``url`` under the network policy above. Returns ``(data, info)`` where info holds
    the final ``url``, ``bytes``, ``sha256``, ``fetched_at`` and, after redirects, ``requested_url``.
    ``allow_list=False`` (content packs, Figma images: hosts Vixl chose, not the caller) skips
    ``VIXL_FETCH_HOSTS``."""
    network_allowed(f"{label} download")
    current = url.strip() if isinstance(url, str) else url
    deadline = time.monotonic() + TOTAL_TIMEOUT
    for hop in range(MAX_REDIRECTS + 1):
        parts = check_url(current, label, allow_list=allow_list)
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


def post_bounded(url, content, headers, *, label="Webhook", allow_list=False, loopback_http=False, limit=65536):
    """POST ``content`` (bytes) to ``url`` under the network policy above and return ``{"status": HTTP status}``.
    A redirect is not followed (it is returned as its status), and at most ``limit`` bytes of the answer are read and
    dropped. Transport failures raise ``fetch_failed``."""
    network_allowed(f"{label} delivery")
    parts = check_url(url, label, allow_list=allow_list, loopback_http=loopback_http)
    proxied = parts.scheme.lower() == "https" and _proxied(parts.hostname)
    address = _target(parts, proxied, label)
    client = httpx.Client(timeout=TIMEOUT, follow_redirects=False, trust_env=proxied)
    try:
        if address is None:
            request = client.build_request("POST", url.strip(), content=content,
                                           headers={**headers, "User-Agent": "vixl"})
        else:
            request = _pinned_request(client, parts, address, "*/*", "POST", content, headers)
        response = client.send(request, stream=True)
        try:
            read = 0
            for chunk in response.iter_bytes():
                read += len(chunk)
                if read > limit:
                    break
            return {"status": response.status_code}
        finally:
            response.close()
    except httpx.HTTPError as exc:
        raise VixlError("fetch_failed", f"{label} delivery failed ({type(exc).__name__})", field="url") from exc
    finally:
        client.close()
