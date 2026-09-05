"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Cross-site request forgery, and the one surface it applies to.

The rule that decides everything here: **a token defends ambient authority, and
only ambient authority needs defending.** A session cookie is sent by the
browser whether or not the page that triggered the request came from us, so a
mutating call authenticated by cookie can be caused by somebody else's page. An
`Authorization: Basic` header is not sent by the browser on anybody's behalf; a
caller who can set it already holds the credential, and asking them for a token
as well protects nothing while breaking every service client.

So the check applies to exactly one case — a state-changing method whose
authority came from the session cookie — and to nothing else. Getting that
boundary right is most of the work; the token itself is ordinary.

**Why this exists when the cookie is already `SameSite=Strict`.** Because that
is one defence, implemented by somebody else's software, and it is not the one
an examiner will accept as sufficient. `SameSite` is enforced by the browser: a
client that does not implement it, an intermediary that strips the attribute, or
a future relaxation of the default takes the whole control away, and its removal
is invisible from here. Defence in depth is not a slogan in that situation — it
is the difference between a control we enforce and a control we hope for.

**Why the token is per session rather than per form.** A per-form (single-use)
token breaks the back button, breaks two tabs, and breaks every page here that
issues several `POST`s from one render — and each of those breakages teaches
somebody to work around the control rather than with it. A control people route
around is worse than one they never had, because it also reports success. The
session token rotates when the session does, which is at sign-in.
"""
from __future__ import annotations

import hmac
import secrets
from typing import Optional

from core.log import get_logger

logger = get_logger(__name__)

SESSION_KEY = "csrf_token"
HEADER = "x-maya-csrf"
FORM_FIELD = "csrf_token"

# Methods that cannot change anything, and are therefore not worth a token. HEAD
# and OPTIONS are here for the same reason GET is; TRACE is not, because this
# application never serves it.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Paths exempt because they *establish* the session rather than act under one.
# A sign-in form has no session to carry a token from, and requiring one would
# make the first request of every visit fail. Each entry is an exact path, never
# a prefix: a prefix exemption grows silently as routes are added beneath it.
EXEMPT_PATHS = frozenset({"/login", "/auth/login", "/auth/callback"})

TOKEN_BYTES = 32


def token_for(session) -> str:
    """The session's token, minted on first ask.

    Minting lazily rather than at sign-in means a session created before this
    existed still gets one, and there is no upgrade step whose absence would
    silently disable the check for everybody already signed in.
    """
    token = session.get(SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(TOKEN_BYTES)
        session[SESSION_KEY] = token
    return token


def presented(request) -> Optional[str]:
    """The token the caller sent, from the header or a form field."""
    if (header := request.headers.get(HEADER)):
        return header
    # A form post cannot set a header, so the field is the only route for the
    # handful of pages that submit without JavaScript.
    form = getattr(request, "_maya_form", None)
    return form.get(FORM_FIELD) if form else None


def required_for(request) -> bool:
    """Whether this request must carry a token.

    Three conditions, all of them necessary:

    * the method changes something,
    * the path is not one that establishes a session,
    * and the authority is **ambient** — a session cookie rather than a
      credential the caller had to hold and present.

    The third is the one that matters. Requiring a token from a Basic-auth
    service client would protect nothing (the browser never sends that header
    unprompted) and would break every engine and script, which is how a security
    control ends up disabled in configuration.
    """
    if request.method.upper() in SAFE_METHODS:
        return False
    if request.url.path in EXEMPT_PATHS:
        return False
    return bool(request.session.get("username"))


def matches(expected: Optional[str], supplied: Optional[str]) -> bool:
    """Constant-time comparison, because a token is a secret.

    A byte-by-byte `==` on a secret leaks its prefix through timing. That is a
    thin channel over HTTP and it is free to close, and "the attack is hard" is
    not a reason to leave a comparison wrong in the one place the codebase
    compares secrets.
    """
    if not expected or not supplied:
        return False
    return hmac.compare_digest(expected, supplied)
