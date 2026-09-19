"""
A test SAML identity provider: a real RSA key and self-signed certificate made at
test time, and Responses whose assertions are signed with xmlsec (through
python3-saml's own signing helper). Every field a service provider must check
can be overridden, so each check can be attacked with a Response that fails
exactly that one.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import base64
import datetime as dt
import uuid
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

IDP = "https://idp.example.test/saml"
SP = "https://maya.example.test/saml"
ACS = "http://127.0.0.1:8600/auth/sso/saml/acs"


def _cert(key: Any, cn: str) -> str:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30)).sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _pem_key(key: Any) -> str:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def _t(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


class SamlIdP:
    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.cert = _cert(self.key, "idp.example.test")
        self.rogue = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.rogue_cert = _cert(self.rogue, "rogue.example.test")

    def argv(self) -> list[str]:
        cert = "".join(line for line in self.cert.splitlines() if "CERTIFICATE" not in line)
        return ["--auth.mode=hybrid", "--auth.sso.protocol=saml2",
                f"--auth.sso.saml.sp_entity_id={SP}", f"--auth.sso.saml.acs_url={ACS}",
                f"--auth.sso.saml.idp_entity_id={IDP}",
                "--auth.sso.saml.idp_sso_url=https://idp.example.test/sso",
                f"--auth.sso.saml.idp_cert={cert}"]

    def response(self, request_id: str | None, username: str = "sara", *,
                 groups: tuple[str, ...] = ("maya-admins",), audience: str = SP,
                 issuer: str = IDP, recipient: str = ACS, destination: str = ACS,
                 not_on_or_after: dt.datetime | None = None, rogue: bool = False,
                 unsigned: bool = False, assertion_id: str | None = None) -> str:
        from onelogin.saml2.constants import OneLogin_Saml2_Constants as C
        from onelogin.saml2.utils import OneLogin_Saml2_Utils
        now = dt.datetime.now(dt.timezone.utc)
        until = not_on_or_after or now + dt.timedelta(minutes=5)
        irt = f' InResponseTo="{request_id}"' if request_id else ""
        values = "".join(f"<saml:AttributeValue>{g}</saml:AttributeValue>" for g in groups)
        assertion = (
            '<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
            f'ID="{assertion_id or "_a" + uuid.uuid4().hex}" Version="2.0" '
            f'IssueInstant="{_t(now)}">'
            f"<saml:Issuer>{issuer}</saml:Issuer>"
            "<saml:Subject><saml:NameID "
            'Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified">'
            f"{username}</saml:NameID>"
            '<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
            f'<saml:SubjectConfirmationData NotOnOrAfter="{_t(until)}" '
            f'Recipient="{recipient}"{irt}/></saml:SubjectConfirmation></saml:Subject>'
            f'<saml:Conditions NotBefore="{_t(now - dt.timedelta(minutes=1))}" '
            f'NotOnOrAfter="{_t(until)}"><saml:AudienceRestriction>'
            f"<saml:Audience>{audience}</saml:Audience></saml:AudienceRestriction>"
            "</saml:Conditions>"
            f'<saml:AuthnStatement AuthnInstant="{_t(now)}" SessionIndex="_s1">'
            "<saml:AuthnContext><saml:AuthnContextClassRef>"
            "urn:oasis:names:tc:SAML:2.0:ac:classes:Password</saml:AuthnContextClassRef>"
            "</saml:AuthnContext></saml:AuthnStatement>"
            '<saml:AttributeStatement><saml:Attribute Name="groups">'
            f"{values}</saml:Attribute>"
            f'<saml:Attribute Name="email"><saml:AttributeValue>{username}@example.test'
            "</saml:AttributeValue></saml:Attribute></saml:AttributeStatement>"
            "</saml:Assertion>")
        if not unsigned:
            key, cert = (self.rogue, self.rogue_cert) if rogue else (self.key, self.cert)
            signed = OneLogin_Saml2_Utils.add_sign(assertion, _pem_key(key), cert,
                                                   sign_algorithm=C.RSA_SHA256,
                                                   digest_algorithm=C.SHA256)
            assertion = signed.decode() if isinstance(signed, bytes) else signed
            if assertion.startswith("<?xml"):
                assertion = assertion.split("?>", 1)[1]
        response = (
            '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
            'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
            f'ID="_r{uuid.uuid4().hex}" Version="2.0" IssueInstant="{_t(now)}" '
            f'Destination="{destination}"{irt}>'
            f"<saml:Issuer>{issuer}</saml:Issuer>"
            '<samlp:Status><samlp:StatusCode '
            'Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
            f"{assertion}</samlp:Response>")
        return base64.b64encode(response.encode()).decode()
