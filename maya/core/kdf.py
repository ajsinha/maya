"""
Password key derivation seam (§13.4.2, *recorded*).

Argon2id is preferred (memory 64 MB, time 3, parallelism 4, §12); stdlib
``hashlib.scrypt`` and then PBKDF2-HMAC-SHA512 are the fallbacks. The
algorithm and its parameters are stored alongside every hash, never assumed
globally, so a hash made under one backend still verifies under another, and
``needs_rehash`` lets a login upgrade it to the strongest available.

Stored form: ``<algorithm>$<json params>$<encoded hash>``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

from maya.core.backends import Backends

ARGON2_PARAMS = {"m": 65536, "t": 3, "p": 4}
SCRYPT_PARAMS = {"n": 2**14, "r": 8, "p": 1}
PBKDF2_PARAMS = {"iterations": 600_000}
STRENGTH = {"argon2id": 3, "scrypt": 2, "pbkdf2_sha512": 1}


def current_algorithm() -> str:
    selected = Backends.selected("kdf")
    return {"argon2id": "argon2id", "scrypt": "scrypt"}.get(selected, "pbkdf2_sha512")


def hash_password(password: str, algorithm: str | None = None) -> str:
    """Hash with the strongest available (or the named) algorithm."""
    algorithm = algorithm or current_algorithm()
    if algorithm == "argon2id":
        from argon2 import PasswordHasher

        ph = PasswordHasher(
            time_cost=ARGON2_PARAMS["t"],
            memory_cost=ARGON2_PARAMS["m"],
            parallelism=ARGON2_PARAMS["p"],
        )
        return f"argon2id${json.dumps(ARGON2_PARAMS, sort_keys=True)}${ph.hash(password)}"
    salt = os.urandom(16)
    if algorithm == "scrypt":
        p = SCRYPT_PARAMS
        dk = hashlib.scrypt(password.encode(), salt=salt, n=p["n"], r=p["r"], p=p["p"])
    else:
        algorithm, p = "pbkdf2_sha512", PBKDF2_PARAMS
        dk = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, p["iterations"])
    enc = base64.b64encode(salt).decode() + ":" + base64.b64encode(dk).decode()
    return f"{algorithm}${json.dumps(p, sort_keys=True)}${enc}"


def verify_password(password: str, stored: str) -> bool:
    """Verify under the algorithm recorded with the hash, whatever is current."""
    try:
        algorithm, params_json, encoded = stored.split("$", 2)
        params = json.loads(params_json)
    except ValueError:
        return False
    if algorithm == "argon2id":
        if not _argon2_importable():
            return False
        from argon2 import PasswordHasher
        from argon2.exceptions import VerificationError, InvalidHashError

        try:
            return bool(PasswordHasher().verify(encoded, password))
        except (VerificationError, InvalidHashError):
            return False
    salt_b64, dk_b64 = encoded.split(":", 1)
    salt, expected = base64.b64decode(salt_b64), base64.b64decode(dk_b64)
    if algorithm == "scrypt":
        dk = hashlib.scrypt(
            password.encode(), salt=salt, n=params["n"], r=params["r"], p=params["p"]
        )
    elif algorithm == "pbkdf2_sha512":
        dk = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, params["iterations"])
    else:
        return False
    return hmac.compare_digest(dk, expected)


def _argon2_importable() -> bool:
    from maya.core.backends import has_module

    return has_module("argon2")


def needs_rehash(stored: str) -> bool:
    """True when a stronger algorithm than the stored one is now available."""
    algorithm = stored.split("$", 1)[0]
    return STRENGTH.get(algorithm, 0) < STRENGTH[current_algorithm()]


def algorithm_of(stored: str) -> str:
    return stored.split("$", 1)[0]
