from __future__ import annotations

import ipaddress
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def detect_local_ip() -> str:
    candidates: list[str] = []
    try:
        candidates.extend(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass

    for candidate in candidates:
        if candidate and not candidate.startswith("127."):
            return candidate

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def ensure_self_signed_cert(cert_dir: Path, local_host: str) -> tuple[Path, Path]:
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "server.crt"
    key_path = cert_dir / "server.key"
    if cert_path.exists() and key_path.exists() and _cert_matches_host(cert_path, local_host):
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TEASR"),
            x509.NameAttribute(NameOID.COMMON_NAME, local_host),
        ]
    )

    alt_names: list[x509.GeneralName] = [x509.DNSName("localhost")]
    host_name = _dns_name_or_none(socket.gethostname())
    if host_name is not None:
        alt_names.append(host_name)

    try:
        alt_names.append(x509.IPAddress(ipaddress.ip_address(local_host)))
    except ValueError:
        dns_name = _dns_name_or_none(local_host)
        if dns_name is not None:
            alt_names.append(dns_name)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(_dedupe_general_names(alt_names)), critical=False)
        .sign(key, hashes.SHA256())
    )

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


def _cert_matches_host(cert_path: Path, host: str) -> bool:
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except Exception:
        return False

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        encoded_host = _encode_dns_label(host)
        if encoded_host is None:
            return False
        return any(
            isinstance(name, x509.DNSName) and name.value.lower() == encoded_host.lower()
            for name in san
        )

    return any(isinstance(name, x509.IPAddress) and name.value == ip for name in san)


def _dns_name_or_none(value: str) -> x509.DNSName | None:
    encoded = _encode_dns_label(value)
    if encoded is None:
        return None
    return x509.DNSName(encoded)


def _encode_dns_label(value: str) -> str | None:
    try:
        return value.encode("idna").decode("ascii")
    except UnicodeError:
        return None


def _dedupe_general_names(names: list[x509.GeneralName]) -> list[x509.GeneralName]:
    deduped: list[x509.GeneralName] = []
    seen: set[tuple[str, str]] = set()
    for name in names:
        if isinstance(name, x509.DNSName):
            key = ("dns", name.value.lower())
        elif isinstance(name, x509.IPAddress):
            key = ("ip", str(name.value))
        else:
            key = (type(name).__name__, repr(name))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(name)
    return deduped
