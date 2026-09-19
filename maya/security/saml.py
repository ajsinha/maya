"""
SAML 2.0 Web SSO, service-provider side (§12): the protocol only.

The only module that imports ``python3-saml`` (``onelogin``) and, through it,
the native ``xmlsec`` binding. Turning a verified assertion into a MAYA
principal lives in ``maya.services.sso``, shared with OIDC.

SP-initiated only. MAYA sends an unsigned AuthnRequest by HTTP-Redirect and
accepts the Response by HTTP-POST at its assertion consumer service (ACS). What
a Response must satisfy before MAYA believes a word of it — all enforced by
python3-saml in strict mode unless noted:

* the **assertion is signed** by the certificate configured for the IdP
  (``wantAssertionsSigned``), with a non-deprecated algorithm;
* ``Issuer`` is the configured IdP entity id; the ``Audience`` names MAYA's
  entity id; ``Destination`` and the ``Recipient`` are MAYA's ACS URL;
* ``NotBefore`` / ``NotOnOrAfter`` hold now;
* ``InResponseTo`` is present and names an AuthnRequest MAYA issued, has not
  expired and has not already been answered — checked here and in the SSO
  service, because python3-saml accepts a Response with no InResponseTo at all
  (an *unsolicited* response), which MAYA refuses.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from maya.core.errors import CapabilityRefused, NotAuthenticated, ValidationFailed

REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
UNSPECIFIED = "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
PACKAGES = "'python3-saml' and 'xmlsec'"


def available() -> bool:
    from maya.core.backends import has_module
    return has_module("onelogin.saml2") and has_module("xmlsec")


def require() -> None:
    if not available():
        raise CapabilityRefused(f"auth.sso.protocol is 'saml2', which needs {PACKAGES} "
                                "(pip install python3-saml xmlsec)", wanted="python3-saml")


@dataclass
class SamlSettings:
    sp_entity_id: str
    acs_url: str
    idp_entity_id: str
    idp_sso_url: str
    idp_cert: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "strict": True, "debug": False,
            "sp": {"entityId": self.sp_entity_id, "NameIDFormat": UNSPECIFIED,
                   "assertionConsumerService": {"url": self.acs_url, "binding": POST}},
            "idp": {"entityId": self.idp_entity_id, "x509cert": self.idp_cert,
                    "singleSignOnService": {"url": self.idp_sso_url, "binding": REDIRECT}},
            "security": {"wantAssertionsSigned": True, "wantMessagesSigned": False,
                         "wantNameId": True, "rejectDeprecatedAlgorithm": True,
                         "requestedAuthnContext": False, "wantAttributeStatement": False,
                         "rejectUnsolicitedResponsesWithInResponseTo": True},
        }


def settings_from(props: Any) -> SamlSettings:
    """SAML settings from configuration — every value required, none defaulted silently."""
    get = lambda key: (props.get(f"auth.sso.saml.{key}") or "").strip()  # noqa: E731
    cert = get("idp_cert")
    if not cert and get("idp_cert_file"):
        with open(get("idp_cert_file"), encoding="utf-8") as fh:
            cert = fh.read()
    cfg = SamlSettings(sp_entity_id=get("sp_entity_id"), acs_url=get("acs_url"),
                       idp_entity_id=get("idp_entity_id"), idp_sso_url=get("idp_sso_url"),
                       idp_cert=_pem_body(cert))
    missing = [k for k, v in (("sp_entity_id", cfg.sp_entity_id), ("acs_url", cfg.acs_url),
                              ("idp_entity_id", cfg.idp_entity_id),
                              ("idp_sso_url", cfg.idp_sso_url), ("idp_cert", cfg.idp_cert))
               if not v]
    if missing:
        raise ValidationFailed("SAML SSO needs " + ", ".join(f"auth.sso.saml.{m}"
                                                             for m in missing))
    return cfg


def _pem_body(pem: str) -> str:
    return "".join(line.strip() for line in pem.splitlines()
                   if line.strip() and "CERTIFICATE" not in line)


def _request_data(acs_url: str, post: dict[str, str] | None = None) -> dict[str, Any]:
    """python3-saml derives "the current URL" from request data; MAYA pins it to the ACS,
    so Destination and Recipient are checked against configuration, not a Host header."""
    u = urlparse(acs_url)
    https = u.scheme == "https"
    return {"https": "on" if https else "off", "http_host": u.hostname or "",
            "server_port": str(u.port or (443 if https else 80)), "script_name": u.path,
            "get_data": {}, "post_data": post or {}}


def in_response_to(saml_response: str) -> str | None:
    """The (not yet verified) InResponseTo of a base64 Response, to find its request."""
    require()
    from onelogin.saml2.utils import OneLogin_Saml2_XML
    try:
        doc = OneLogin_Saml2_XML.to_etree(base64.b64decode(saml_response))
    except Exception as exc:  # noqa: BLE001 - malformed input is one answer: not a Response
        raise NotAuthenticated("The SAML response is not well-formed") from exc
    return doc.get("InResponseTo") or None


class SamlSP:
    def __init__(self, cfg: SamlSettings) -> None:
        require()
        from onelogin.saml2.settings import OneLogin_Saml2_Settings
        self.cfg = cfg
        self.settings = OneLogin_Saml2_Settings(cfg.as_dict(), sp_validation_only=True)

    def begin(self, relay_state: str = "") -> dict[str, str]:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
        auth = OneLogin_Saml2_Auth(_request_data(self.cfg.acs_url), self.settings)
        url = auth.login(return_to=relay_state or None)
        return {"redirect_url": url, "request_id": auth.get_last_request_id()}

    def finish(self, saml_response: str, request_id: str) -> dict[str, Any]:
        """Validate a Response to ``request_id``; return the identity it asserts."""
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
        if not request_id:
            raise NotAuthenticated("Unsolicited SAML response refused: it answers no request "
                                   "MAYA made")
        auth = OneLogin_Saml2_Auth(_request_data(self.cfg.acs_url,
                                                 {"SAMLResponse": saml_response}), self.settings)
        try:
            auth.process_response(request_id=request_id)
        except Exception as exc:  # noqa: BLE001 - python3-saml raises for malformed input
            raise NotAuthenticated(f"The SAML response is invalid: {exc}") from exc
        if auth.get_errors() or not auth.is_authenticated():
            raise NotAuthenticated("The SAML response is invalid: "
                                   f"{auth.get_last_error_reason() or ', '.join(auth.get_errors())}")
        return {"name_id": auth.get_nameid(), "attributes": auth.get_attributes(),
                "assertion_id": auth.get_last_assertion_id(),
                "not_on_or_after": auth.get_last_assertion_not_on_or_after(),
                "session_index": auth.get_session_index(), "issuer": self.cfg.idp_entity_id}

    def metadata(self) -> str:
        xml = self.settings.get_sp_metadata()
        errors = self.settings.validate_metadata(xml)
        if errors:
            raise ValidationFailed("SP metadata is invalid: " + ", ".join(errors))
        return xml.decode() if isinstance(xml, bytes) else xml
