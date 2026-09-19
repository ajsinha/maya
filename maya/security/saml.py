"""
SAML 2.0 Web SSO, service-provider side (§12): the protocol only.

The only module that imports ``python3-saml`` (``onelogin``) and, through it,
the native ``xmlsec`` binding. Turning a verified assertion into a MAYA
principal lives in ``maya.services.sso``, shared with OIDC.

SP-initiated sign-in. MAYA sends an AuthnRequest by HTTP-Redirect — signed with
MAYA's own key pair when ``sign_requests`` is on — and accepts the Response by
HTTP-POST at its assertion consumer service (ACS). What a Response must satisfy
before MAYA believes a word of it — all enforced by python3-saml in strict mode
unless noted:

* the **assertion is signed** by the certificate configured for the IdP
  (``wantAssertionsSigned``), with a non-deprecated algorithm;
* ``Issuer`` is the configured IdP entity id; the ``Audience`` names MAYA's
  entity id; ``Destination`` and the ``Recipient`` are MAYA's ACS URL;
* ``NotBefore`` / ``NotOnOrAfter`` hold now;
* ``InResponseTo`` is present and names an AuthnRequest MAYA issued, has not
  expired and has not already been answered — checked here and in the SSO
  service, because python3-saml accepts a Response with no InResponseTo at all
  (an *unsolicited* response), which MAYA refuses.

Single logout (when ``idp_slo_url`` is set), HTTP-Redirect both ways, at MAYA's
single logout service (SLS):

* **MAYA-initiated** — signing out ends the MAYA session, then sends the browser
  to the IdP with a LogoutRequest naming the NameID and SessionIndex of the sign-in;
  the IdP's LogoutResponse must answer that request (``InResponseTo``).
* **IdP-initiated** — a LogoutRequest from the IdP must be **signed** (MAYA
  refuses an unsigned one: it would let anyone end anyone's sessions), from the
  configured issuer, addressed to the SLS; MAYA ends every session of that
  NameID (and SessionIndex, when named) and answers with a LogoutResponse.

Redirect-binding signatures are checked over the query string exactly as the IdP
sent it, so an IdP's own URL encoding cannot break them.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

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


RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"


@dataclass
class SamlSettings:
    sp_entity_id: str
    acs_url: str
    idp_entity_id: str
    idp_sso_url: str
    idp_cert: str
    idp_slo_url: str = ""
    sls_url: str = ""
    sign_requests: bool = False
    sp_cert: str = ""
    sp_key: str = ""

    @property
    def slo(self) -> bool:
        return bool(self.idp_slo_url)

    def as_dict(self) -> dict[str, Any]:
        sp: dict[str, Any] = {"entityId": self.sp_entity_id, "NameIDFormat": UNSPECIFIED,
                              "assertionConsumerService": {"url": self.acs_url,
                                                           "binding": POST}}
        idp: dict[str, Any] = {"entityId": self.idp_entity_id, "x509cert": self.idp_cert,
                               "singleSignOnService": {"url": self.idp_sso_url,
                                                       "binding": REDIRECT}}
        if self.slo:
            sp["singleLogoutService"] = {"url": self.sls_url, "binding": REDIRECT}
            idp["singleLogoutService"] = {"url": self.idp_slo_url, "binding": REDIRECT}
        if self.sp_cert:
            sp["x509cert"] = self.sp_cert
        if self.sp_key:
            sp["privateKey"] = self.sp_key
        return {
            "strict": True, "debug": False, "sp": sp, "idp": idp,
            "security": {"wantAssertionsSigned": True, "wantMessagesSigned": False,
                         "wantNameId": True, "rejectDeprecatedAlgorithm": True,
                         "requestedAuthnContext": False, "wantAttributeStatement": False,
                         "rejectUnsolicitedResponsesWithInResponseTo": True,
                         "authnRequestsSigned": self.sign_requests,
                         "logoutRequestSigned": self.sign_requests,
                         "logoutResponseSigned": self.sign_requests,
                         "signatureAlgorithm": RSA_SHA256, "digestAlgorithm": SHA256},
        }


def settings_from(props: Any) -> SamlSettings:
    """SAML settings from configuration — every value required, none defaulted silently."""
    get = lambda key: (props.get(f"auth.sso.saml.{key}") or "").strip()  # noqa: E731

    def inline_or_file(key: str) -> str:
        if get(key):
            return get(key)
        if get(f"{key}_file"):
            with open(get(f"{key}_file"), encoding="utf-8") as fh:
                return fh.read()
        return ""
    cfg = SamlSettings(sp_entity_id=get("sp_entity_id"), acs_url=get("acs_url"),
                       idp_entity_id=get("idp_entity_id"), idp_sso_url=get("idp_sso_url"),
                       idp_cert=_pem_body(inline_or_file("idp_cert")),
                       idp_slo_url=get("idp_slo_url"), sls_url=get("sls_url"),
                       sign_requests=get("sign_requests").lower() in ("true", "1", "yes"),
                       sp_cert=_pem_body(inline_or_file("sp_cert")),
                       sp_key=inline_or_file("sp_key").strip())
    required = [("sp_entity_id", cfg.sp_entity_id), ("acs_url", cfg.acs_url),
                ("idp_entity_id", cfg.idp_entity_id), ("idp_sso_url", cfg.idp_sso_url),
                ("idp_cert", cfg.idp_cert)]
    if cfg.slo:
        required.append(("sls_url", cfg.sls_url))
    if cfg.sign_requests:
        required += [("sp_cert", cfg.sp_cert), ("sp_key", cfg.sp_key)]
    missing = [k for k, v in required if not v]
    if missing:
        raise ValidationFailed("SAML SSO needs " + ", ".join(f"auth.sso.saml.{m}"
                                                             for m in missing))
    return cfg


def _pem_body(pem: str) -> str:
    return "".join(line.strip() for line in pem.splitlines()
                   if line.strip() and "CERTIFICATE" not in line)


def _request_data(url: str, post: dict[str, str] | None = None,
                  query_string: str = "") -> dict[str, Any]:
    """python3-saml derives "the current URL" from request data; MAYA pins it to the ACS
    (or the SLS), so Destination and Recipient are checked against configuration, not a
    Host header. A redirect-binding message is read, and its signature checked, from
    the query string exactly as received."""
    u = urlparse(url)
    https = u.scheme == "https"
    data: dict[str, Any] = {"https": "on" if https else "off", "http_host": u.hostname or "",
                            "server_port": str(u.port or (443 if https else 80)),
                            "script_name": u.path, "get_data": {}, "post_data": post or {}}
    if query_string:
        data["get_data"] = {k: v[0] for k, v in parse_qs(query_string).items()}
        data["query_string"] = query_string
        data["validate_signature_from_qs"] = True
    return data


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

    # -- single logout -------------------------------------------------------------
    def logout(self, name_id: str, session_index: str | None,
               relay_state: str = "") -> dict[str, str]:
        """A LogoutRequest for the sign-in that made a session: where to send the browser."""
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
        auth = OneLogin_Saml2_Auth(_request_data(self.cfg.sls_url), self.settings)
        url = auth.logout(return_to=relay_state or None, name_id=name_id,
                          session_index=session_index, name_id_format=UNSPECIFIED)
        return {"redirect_url": url, "request_id": auth.get_last_request_id()}

    @staticmethod
    def message_kind(query_string: str) -> str:
        """``request`` (the IdP asks MAYA to end sessions) or ``response`` (the IdP
        answers MAYA's LogoutRequest)."""
        keys = parse_qs(query_string)
        if "SAMLRequest" in keys:
            return "request"
        if "SAMLResponse" in keys:
            return "response"
        raise NotAuthenticated("No SAML logout message: expected SAMLRequest or SAMLResponse")

    @staticmethod
    def logout_response_to(query_string: str) -> str | None:
        """The (not yet verified) InResponseTo of a LogoutResponse, to find MAYA's request."""
        from onelogin.saml2.utils import OneLogin_Saml2_Utils, OneLogin_Saml2_XML
        try:
            raw = parse_qs(query_string)["SAMLResponse"][0]
            doc = OneLogin_Saml2_XML.to_etree(OneLogin_Saml2_Utils.decode_base64_and_inflate(raw))
        except Exception as exc:  # noqa: BLE001 - malformed input: not a LogoutResponse
            raise NotAuthenticated("The SAML logout response is not well-formed") from exc
        return doc.get("InResponseTo") or None

    def finish_logout(self, query_string: str, request_id: str) -> None:
        """Validate the IdP's LogoutResponse to MAYA's LogoutRequest ``request_id``."""
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
        auth = OneLogin_Saml2_Auth(_request_data(self.cfg.sls_url, query_string=query_string),
                                   self.settings)
        try:
            auth.process_slo(keep_local_session=True, request_id=request_id)
        except Exception as exc:  # noqa: BLE001 - python3-saml raises for malformed input
            raise NotAuthenticated(f"The SAML logout response is invalid: {exc}") from exc
        if auth.get_errors():
            raise NotAuthenticated("The SAML logout response is invalid: "
                                   f"{auth.get_last_error_reason() or ', '.join(auth.get_errors())}")

    def accept_logout(self, query_string: str) -> dict[str, Any]:
        """Validate an IdP-initiated LogoutRequest; return whom it signs out and the
        LogoutResponse redirect. Unsigned requests are refused."""
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
        from onelogin.saml2.logout_request import OneLogin_Saml2_Logout_Request
        if "Signature" not in parse_qs(query_string):
            raise NotAuthenticated("Unsigned SAML LogoutRequest refused: MAYA ends sessions "
                                   "only on a request signed by the IdP")
        auth = OneLogin_Saml2_Auth(_request_data(self.cfg.sls_url, query_string=query_string),
                                   self.settings)
        try:
            url = auth.process_slo(keep_local_session=True)
        except Exception as exc:  # noqa: BLE001 - python3-saml raises for malformed input
            raise NotAuthenticated(f"The SAML logout request is invalid: {exc}") from exc
        if auth.get_errors() or not url:
            raise NotAuthenticated("The SAML logout request is invalid: "
                                   f"{auth.get_last_error_reason() or ', '.join(auth.get_errors())}")
        xml = auth.get_last_request_xml()
        return {"name_id": OneLogin_Saml2_Logout_Request.get_nameid(xml),
                "session_indexes": OneLogin_Saml2_Logout_Request.get_session_indexes(xml),
                "redirect_url": url}

    def metadata(self) -> str:
        xml = self.settings.get_sp_metadata()
        errors = self.settings.validate_metadata(xml)
        if errors:
            raise ValidationFailed("SP metadata is invalid: " + ", ".join(errors))
        return xml.decode() if isinstance(xml, bytes) else xml
