from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


BLOCKED_HOSTS = {"localhost", "127.0.0.1", "::1"}
BLOCKED_CLOUD_IPS = {ipaddress.ip_address("169.254.169.254")}
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower().lstrip(".")


def _domain_matches(hostname: str, domain: str) -> bool:
    host = _normalize_domain(hostname)
    check = _normalize_domain(domain)
    return host == check or host.endswith(f".{check}")


def _ip_is_blocked(ip: IPAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or ip in BLOCKED_CLOUD_IPS
    )


def _hostname_is_literal_ip(hostname: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        return None


def validate_url_basic(
    url: str,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
) -> tuple[bool, str | None, str | None]:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False, "Only http and https URLs are allowed", None

        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            return False, "URL must include a hostname", None

        if hostname in BLOCKED_HOSTS:
            return False, f"Blocked hostname: {hostname}", hostname

        literal_ip = _hostname_is_literal_ip(hostname)
        if literal_ip and _ip_is_blocked(literal_ip):
            return False, f"Blocked IP address: {literal_ip}", hostname

        if blocked_domains:
            for domain in blocked_domains:
                if _domain_matches(hostname, domain):
                    return False, f"Blocked domain: {domain}", hostname

        if allowed_domains:
            if not any(_domain_matches(hostname, domain) for domain in allowed_domains):
                return False, f"Domain not in allowlist: {hostname}", hostname

        return True, None, hostname
    except Exception as e:
        return False, str(e), None


def validate_url_for_fetch(
    url: str,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
) -> tuple[bool, str | None, str | None]:
    ok, error, hostname = validate_url_basic(
        url=url,
        allowed_domains=allowed_domains,
        blocked_domains=blocked_domains,
    )
    if not ok or not hostname:
        return ok, error, hostname

    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False, f"Could not resolve hostname: {hostname}", hostname

    for entry in addresses:
        ip_str = entry[4][0]
        ip_obj = ipaddress.ip_address(ip_str)
        if _ip_is_blocked(ip_obj):
            return False, f"Resolved to blocked IP: {ip_obj}", hostname

    return True, None, hostname

    return True, None, hostname
