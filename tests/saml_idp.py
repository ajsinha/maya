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
SLS = "http://127.0.0.1:8600/auth/sso/saml/sls"
IDP_SLO = "https://idp.example.test/slo"
RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"


def _cert(key: Any, cn: str) -> str:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _pem_key(key: Any) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def _t(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


class SamlIdP:
    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.cert = _cert(self.key, "idp.example.test")
        self.rogue = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.rogue_cert = _cert(self.rogue, "rogue.example.test")

    def argv(self, *, slo: bool = False, sp_files: tuple[str, str] | None = None) -> list[str]:
        """Settings for a MAYA that trusts this IdP; ``slo`` adds single logout and
        ``sp_files`` (cert path, key path) turns on signed requests with that key pair."""
        cert = "".join(line for line in self.cert.splitlines() if "CERTIFICATE" not in line)
        argv = [
            "--auth.mode=hybrid",
            "--auth.sso.protocol=saml2",
            f"--auth.sso.saml.sp_entity_id={SP}",
            f"--auth.sso.saml.acs_url={ACS}",
            f"--auth.sso.saml.idp_entity_id={IDP}",
            "--auth.sso.saml.idp_sso_url=https://idp.example.test/sso",
            f"--auth.sso.saml.idp_cert={cert}",
        ]
        if slo:
            argv += [f"--auth.sso.saml.idp_slo_url={IDP_SLO}", f"--auth.sso.saml.sls_url={SLS}"]
        if sp_files:
            argv += [
                "--auth.sso.saml.sign_requests=true",
                f"--auth.sso.saml.sp_cert_file={sp_files[0]}",
                f"--auth.sso.saml.sp_key_file={sp_files[1]}",
            ]
        return argv

    # -- single logout, HTTP-Redirect -------------------------------------------------
    def _redirect(
        self,
        kind: str,
        xml: str,
        *,
        signed: bool = True,
        rogue: bool = False,
        relay_state: str | None = None,
    ) -> str:
        """The query string the IdP would redirect with: deflated, and signed over the
        exact bytes MAYA verifies (SAMLRequest|SAMLResponse, RelayState, SigAlg)."""
        from urllib.parse import quote_plus

        from cryptography.hazmat.primitives.asymmetric import padding
        from onelogin.saml2.utils import OneLogin_Saml2_Utils

        parts = [f"{kind}={quote_plus(OneLogin_Saml2_Utils.deflate_and_base64_encode(xml))}"]
        if relay_state is not None:
            parts.append(f"RelayState={quote_plus(relay_state)}")
        if not signed:
            return "&".join(parts)
        parts.append(f"SigAlg={quote_plus(RSA_SHA256)}")
        key = self.rogue if rogue else self.key
        sig = key.sign("&".join(parts).encode(), padding.PKCS1v15(), hashes.SHA256())
        return "&".join(parts) + "&Signature=" + quote_plus(base64.b64encode(sig).decode())

    def logout_request(
        self,
        name_id: str,
        session_index: str | None = "_s1",
        *,
        destination: str = SLS,
        issuer: str = IDP,
        **kw: Any,
    ) -> str:
        now = dt.datetime.now(dt.timezone.utc)
        index = f"<samlp:SessionIndex>{session_index}</samlp:SessionIndex>" if session_index else ""
        xml = (
            '<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
            'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
            f'ID="_l{uuid.uuid4().hex}" Version="2.0" IssueInstant="{_t(now)}" '
            f'Destination="{destination}"><saml:Issuer>{issuer}</saml:Issuer>'
            '<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified">'
            f"{name_id}</saml:NameID>{index}</samlp:LogoutRequest>"
        )
        return self._redirect("SAMLRequest", xml, **kw)

    def logout_response(self, in_response_to: str, *, destination: str = SLS, **kw: Any) -> str:
        now = dt.datetime.now(dt.timezone.utc)
        xml = (
            '<samlp:LogoutResponse xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
            'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
            f'ID="_lr{uuid.uuid4().hex}" Version="2.0" IssueInstant="{_t(now)}" '
            f'Destination="{destination}" InResponseTo="{in_response_to}">'
            f"<saml:Issuer>{IDP}</saml:Issuer><samlp:Status><samlp:StatusCode "
            'Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
            "</samlp:LogoutResponse>"
        )
        return self._redirect("SAMLResponse", xml, **kw)

    def response(
        self,
        request_id: str | None,
        username: str = "sara",
        *,
        groups: tuple[str, ...] = ("maya-admins",),
        audience: str = SP,
        issuer: str = IDP,
        recipient: str = ACS,
        destination: str = ACS,
        not_on_or_after: dt.datetime | None = None,
        rogue: bool = False,
        unsigned: bool = False,
        assertion_id: str | None = None,
        repeat_attributes: bool = False,
    ) -> str:
        """A signed Response. ``repeat_attributes`` shapes the attribute statement as
        Keycloak does: one same-named Attribute element per group, plus its default
        role-list mapper's one ``Role`` element per role."""
        from onelogin.saml2.constants import OneLogin_Saml2_Constants as C
        from onelogin.saml2.utils import OneLogin_Saml2_Utils

        now = dt.datetime.now(dt.timezone.utc)
        until = not_on_or_after or now + dt.timedelta(minutes=5)
        irt = f' InResponseTo="{request_id}"' if request_id else ""
        values = "".join(f"<saml:AttributeValue>{g}</saml:AttributeValue>" for g in groups)
        group_attrs = f'<saml:Attribute Name="groups">{values}</saml:Attribute>'
        if repeat_attributes:
            group_attrs = "".join(
                f'<saml:Attribute Name="groups"><saml:AttributeValue>{g}'
                "</saml:AttributeValue></saml:Attribute>"
                for g in groups
            ) + "".join(
                f'<saml:Attribute Name="Role"><saml:AttributeValue>{r}'
                "</saml:AttributeValue></saml:Attribute>"
                for r in ("offline_access", "uma_authorization")
            )
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
            f"<saml:AttributeStatement>{group_attrs}"
            f'<saml:Attribute Name="email"><saml:AttributeValue>{username}@example.test'
            "</saml:AttributeValue></saml:Attribute></saml:AttributeStatement>"
            "</saml:Assertion>"
        )
        if not unsigned:
            key, cert = (self.rogue, self.rogue_cert) if rogue else (self.key, self.cert)
            signed = OneLogin_Saml2_Utils.add_sign(
                assertion,
                _pem_key(key),
                cert,
                sign_algorithm=C.RSA_SHA256,
                digest_algorithm=C.SHA256,
            )
            assertion = signed.decode() if isinstance(signed, bytes) else signed
            if assertion.startswith("<?xml"):
                assertion = assertion.split("?>", 1)[1]
        response = (
            '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
            'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
            f'ID="_r{uuid.uuid4().hex}" Version="2.0" IssueInstant="{_t(now)}" '
            f'Destination="{destination}"{irt}>'
            f"<saml:Issuer>{issuer}</saml:Issuer>"
            "<samlp:Status><samlp:StatusCode "
            'Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
            f"{assertion}</samlp:Response>"
        )
        return base64.b64encode(response.encode()).decode()


def sp_key_pair(directory: Any) -> tuple[str, str]:
    """A key pair for MAYA as a service provider, written as PEM files."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert_path, key_path = directory / "sp.crt", directory / "sp.key"
    cert_path.write_text(_cert(key, "maya.example.test"))
    key_path.write_text(_pem_key(key))
    return str(cert_path), str(key_path)
