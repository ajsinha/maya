"""
WebAuthn (security keys and passkeys), relying-party side (§12): the protocol only.

The only module that imports the ``webauthn`` package (py_webauthn). Storing
credentials and challenges, and deciding what a verified ceremony means for a
session, live in ``maya.services.passkeys``.

MAYA uses WebAuthn as a **second factor** after a password, alongside TOTP.
Attestation is not requested (``none``): MAYA records which authenticator model
(AAGUID) a key reports but does not trust-anchor it, so it does not claim a key
is hardware-backed. What each ceremony must satisfy, enforced by py_webauthn:
the challenge MAYA issued, MAYA's origin and relying-party id, user presence,
a signature by the registered public key, and — at authentication — a
signature counter that went up (a cloned key gives itself away by repeating or
lowering it). Algorithms: EdDSA, ES256, RS256.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from maya.core.errors import CapabilityRefused, NotAuthenticated, ValidationFailed


def available() -> bool:
    from maya.core.backends import has_module
    return has_module("webauthn")


def require() -> None:
    if not available():
        raise CapabilityRefused("Security keys need the 'webauthn' package "
                                "(pip install webauthn)", wanted="webauthn")


def b64u(data: bytes) -> str:
    from webauthn.helpers import bytes_to_base64url
    return bytes_to_base64url(data)


def unb64u(text: str) -> bytes:
    from webauthn.helpers import base64url_to_bytes
    return base64url_to_bytes(text)


@dataclass
class RelyingParty:
    rp_id: str
    rp_name: str
    origins: list[str]

    def registration_options(self, user_handle: bytes, username: str, display_name: str,
                             existing: list[dict[str, Any]]) -> tuple[dict[str, Any], bytes]:
        require()
        from webauthn import generate_registration_options, options_to_json
        from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
                                              PublicKeyCredentialDescriptor,
                                              ResidentKeyRequirement, UserVerificationRequirement)
        opts = generate_registration_options(
            rp_id=self.rp_id, rp_name=self.rp_name, user_name=username, user_id=user_handle,
            user_display_name=display_name,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.DISCOURAGED,
                user_verification=UserVerificationRequirement.PREFERRED),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=unb64u(c["credential_id"]))
                                 for c in existing])
        return json.loads(options_to_json(opts)), opts.challenge

    def verify_registration(self, credential: dict[str, Any], challenge: bytes
                            ) -> dict[str, Any]:
        require()
        from webauthn import verify_registration_response
        from webauthn.helpers.exceptions import InvalidRegistrationResponse
        try:
            v = verify_registration_response(credential=credential, expected_challenge=challenge,
                                             expected_rp_id=self.rp_id,
                                             expected_origin=self.origins)
        except (InvalidRegistrationResponse, ValueError, KeyError, TypeError) as exc:
            raise ValidationFailed(f"The security key's registration did not verify: {exc}"
                                   ) from exc
        transports = ((credential.get("response") or {}).get("transports") or [])
        return {"credential_id": b64u(v.credential_id),
                "public_key": b64u(v.credential_public_key), "sign_count": v.sign_count,
                "aaguid": v.aaguid, "backed_up": bool(v.credential_backed_up),
                "transports": [str(t) for t in transports][:8]}

    def authentication_options(self, credentials: list[dict[str, Any]]
                               ) -> tuple[dict[str, Any], bytes]:
        require()
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import (AuthenticatorTransport,
                                              PublicKeyCredentialDescriptor,
                                              UserVerificationRequirement)
        known = {t.value for t in AuthenticatorTransport}
        opts = generate_authentication_options(
            rp_id=self.rp_id, user_verification=UserVerificationRequirement.PREFERRED,
            allow_credentials=[PublicKeyCredentialDescriptor(
                id=unb64u(c["credential_id"]),
                transports=[AuthenticatorTransport(t) for t in c.get("transports") or []
                            if t in known] or None) for c in credentials])
        return json.loads(options_to_json(opts)), opts.challenge

    def verify_authentication(self, credential: dict[str, Any], challenge: bytes,
                              stored: dict[str, Any]) -> int:
        """Verify an assertion by a stored credential; return the new signature counter."""
        require()
        from webauthn import verify_authentication_response
        from webauthn.helpers.exceptions import InvalidAuthenticationResponse
        try:
            v = verify_authentication_response(
                credential=credential, expected_challenge=challenge, expected_rp_id=self.rp_id,
                expected_origin=self.origins, credential_public_key=unb64u(stored["public_key"]),
                credential_current_sign_count=int(stored["sign_count"]))
        except (InvalidAuthenticationResponse, ValueError, KeyError, TypeError) as exc:
            raise NotAuthenticated(f"The security key's response did not verify: {exc}") from exc
        return int(v.new_sign_count)


def challenge_of(credential: dict[str, Any]) -> str:
    """The (not yet verified) challenge a ceremony answers, base64url, to find it."""
    require()
    from webauthn.helpers import parse_client_data_json
    try:
        raw = (credential.get("response") or {})["clientDataJSON"]
        return b64u(parse_client_data_json(unb64u(raw)).challenge)
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise ValidationFailed("The security key's response is malformed") from exc


def relying_party(props: Any) -> RelyingParty:
    rp_id = (props.get("auth.webauthn.rp_id") or "").strip()
    origins = [o.strip() for o in (props.get("auth.webauthn.origins") or "").split(",")
               if o.strip()]
    if not rp_id or not origins:
        raise ValidationFailed("Security keys need auth.webauthn.rp_id and "
                               "auth.webauthn.origins")
    return RelyingParty(rp_id=rp_id, rp_name=props.get("auth.webauthn.rp_name") or "MAYA",
                        origins=origins)
