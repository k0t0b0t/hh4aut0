from __future__ import annotations


def build_verify_and_cert(ssl_cfg: dict):
    verify = ssl_cfg.get("verify_ssl", True)
    ca = ssl_cfg.get("ca_cert_path") or None
    cert = ssl_cfg.get("client_cert_path") or None
    key = ssl_cfg.get("client_key_path") or None
    verify_arg = ca if ca else verify
    cert_arg = (cert, key) if cert and key else cert
    return verify_arg, cert_arg
