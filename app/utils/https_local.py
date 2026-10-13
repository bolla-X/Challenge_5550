"""Certificado autoassinado para HTTPS na rede local (F6: celular como câmera).

O celular só libera a câmera (`getUserMedia`) em contexto seguro, e um IP de
LAN em `http://` não é contexto seguro
(https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts). Este
módulo gera, com o `cryptography` que já é dependência, um certificado
autoassinado com SAN para localhost, 127.0.0.1 e os IPs informados. O celular
mostra o aviso de certificado não confiável uma vez; aceitar é decisão de quem
está segurando o celular.

A chave privada fica em `instance/` (fora do git) e nunca é impressa.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
from pathlib import Path


def garantir_certificado(pasta: Path, ips: list[str], *, dias: int = 30) -> tuple[Path, Path]:
    """(certificado, chave). Reaproveita o existente se ainda cobrir os IPs e não tiver vencido."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    pasta.mkdir(parents=True, exist_ok=True)
    cert_path, chave_path = pasta / "visionepi-local.crt", pasta / "visionepi-local.key"
    alvos = {"127.0.0.1", *[ip for ip in ips if ip]}
    if cert_path.exists() and chave_path.exists():
        try:
            atual = x509.load_pem_x509_certificate(cert_path.read_bytes())
            san = atual.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            cobertos = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
            if alvos <= cobertos and atual.not_valid_after_utc > dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1):
                return cert_path, chave_path
        except (ValueError, x509.ExtensionNotFound):
            pass

    chave = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "VisionEPI local")])
    agora = dt.datetime.now(dt.timezone.utc)
    san = x509.SubjectAlternativeName(
        [x509.DNSName("localhost"), *[x509.IPAddress(ipaddress.ip_address(ip)) for ip in sorted(alvos)]]
    )
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - dt.timedelta(minutes=5))
        .not_valid_after(agora + dt.timedelta(days=dias))
        .add_extension(san, critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(chave, hashes.SHA256())
    )
    chave_path.write_bytes(chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
    cert_path.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    return cert_path, chave_path
