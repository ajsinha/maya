"""
Tamper-evident custody (§29.6): anchoring the audit chain outside MAYA.

The hash chain (§19) proves that the audit log is internally consistent. It does
not stop someone with write access to the database from rewriting history *and
recomputing every hash after it* — the result is consistent too. An anchor pins
the chain head at a sequence number in places the database cannot reach:

* ``signature`` — an Ed25519 signature over ``{seq, head, at}``;
* ``file`` — a JSON line appended to ``custody.anchor.file`` (point it at WORM or
  off-host storage; on the same disk it only raises the bar);
* ``event`` — an ``audit.anchored`` event, so every webhook subscriber holds a
  copy — an external witness MAYA's administrators do not control;
* ``rfc3161`` — a timestamp token from the TSA at ``custody.anchor.tsa_url``
  (off by default: it sends the head hash to a third party).

``verify`` checks each anchor against the live chain. A rewritten history no
longer matches the heads its anchors pinned, even when its own chain verifies.
An RFC 3161 token is checked here for status and message imprint; checking the
TSA's signature needs its certificate chain: with ``custody.anchor.tsa_ca_file`` set
(the TSA's CA certificate, PEM), MAYA checks it on every anchor and every verification
with ``openssl ts -verify``; without it, the report names that command to run by hand.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import base64
import json
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from maya.core import djson
from maya.core.errors import PermissionDenied, ValidationFailed
from maya.core.clock import utcnow
from maya.security.authz import Principal

SHA256_OID = bytes.fromhex("0609608648016503040201")      # 2.16.840.1.101.3.4.2.1


def _der(tag: int, body: bytes) -> bytes:
    n = len(body)
    length = bytes([n]) if n < 128 else bytes([0x80 | ((n.bit_length() + 7) // 8)]) + \
        n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([tag]) + length + body


def timestamp_request(digest: bytes, nonce: int) -> bytes:
    """A DER TimeStampReq (RFC 3161 §2.4.1) for a SHA-256 digest, certReq true."""
    algorithm = _der(0x30, SHA256_OID + b"\x05\x00")
    imprint = _der(0x30, algorithm + _der(0x04, digest))
    nonce_bytes = nonce.to_bytes((nonce.bit_length() + 8) // 8, "big")
    return _der(0x30, b"\x02\x01\x01" + imprint + _der(0x02, nonce_bytes) + b"\x01\x01\xff")


def check_timestamp_response(raw: bytes, digest: bytes) -> dict[str, Any]:
    """Status granted, and the token carries our message imprint."""
    if len(raw) < 8 or raw[0] != 0x30:
        return {"ok": False, "detail": "not a DER TimeStampResp"}
    offset = 2 + (raw[1] & 0x7F if raw[1] & 0x80 else 0)
    status_info = raw[offset:]
    if status_info[:1] != b"\x30":
        return {"ok": False, "detail": "missing PKIStatusInfo"}
    inner = 2 + (status_info[1] & 0x7F if status_info[1] & 0x80 else 0)
    status = status_info[inner:inner + 3]
    if status not in (b"\x02\x01\x00", b"\x02\x01\x01"):
        return {"ok": False, "detail": f"TSA refused (status bytes {status.hex()})"}
    if _der(0x04, digest) not in raw:
        return {"ok": False, "detail": "the token does not carry this head's imprint"}
    return {"ok": True, "detail": "granted; imprint matches. Verify the TSA's signature with "
                                  "'openssl ts -verify -digest <head hash> -in <token> "
                                  "-CAfile <tsa CA>', or set custody.anchor.tsa_ca_file"}


def verify_tsa_signature(raw: bytes, digest: bytes, ca_file: str) -> dict[str, Any]:
    """The TSA's signature over its token, for this imprint, chained to ``ca_file``."""
    openssl = shutil.which("openssl")
    if openssl is None:
        return {"ok": False, "detail": "openssl is not installed, so the TSA's signature "
                                       "cannot be checked"}
    with tempfile.TemporaryDirectory() as tmp:
        token = Path(tmp) / "token.tsr"
        token.write_bytes(raw)
        r = subprocess.run([openssl, "ts", "-verify", "-digest", digest.hex(), "-in",
                            str(token), "-CAfile", ca_file],
                           capture_output=True, text=True, timeout=30, check=False)
    if r.returncode == 0 and "Verification: OK" in r.stdout:
        return {"ok": True, "detail": f"TSA signature verified against {ca_file}"}
    reason = (r.stderr or r.stdout).strip().splitlines()
    return {"ok": False, "detail": "the TSA's signature does not verify: "
                                   + (reason[-1] if reason else f"openssl exit {r.returncode}")}


class CustodyService:
    def __init__(self, platform: Any) -> None:
        self.p = platform
        s = platform.settings
        methods = [m.strip() for m in (s.get("custody.anchor.methods") or
                                         "signature,file,event").split(",") if m.strip()]
        self.methods = [m for m in methods if m in ("signature", "file", "event", "rfc3161")]
        self.tsa_url = (s.get("custody.anchor.tsa_url") or "").strip()
        if "rfc3161" in self.methods and not self.tsa_url:
            raise ValidationFailed("custody.anchor.methods names rfc3161 but "
                                   "custody.anchor.tsa_url is not set")
        self.tsa_ca = (s.get("custody.anchor.tsa_ca_file") or "").strip()
        if self.tsa_ca and not (Path(self.tsa_ca).is_file() and shutil.which("openssl")):
            raise ValidationFailed("custody.anchor.tsa_ca_file needs the CA file to exist "
                                   "and openssl to be installed", tsa_ca_file=self.tsa_ca)
        self.path = Path(s.get("custody.anchor.file") or (platform.root / "anchors.jsonl"))
        self.transport: Any = None                      # tests inject a TSA

    @staticmethod
    def _admin(p: Principal) -> None:
        if not (p.is_admin or "techops" in p.roles):
            raise PermissionDenied("Custody anchoring is for administrators and techops")

    def anchor(self) -> dict[str, Any] | None:
        """Pin the current chain head everywhere configured. None when the log is empty."""
        with self.p.uow("system") as uow:
            chain = uow.repo("audit_events").verify_chain()
            if not chain["ok"]:
                raise ValidationFailed("The audit chain is broken; anchoring it would certify "
                                       "tampering", **chain)
            head = uow.repo("audit_events").list(order_by=["-seq"], limit=1)
        if not head:
            return None
        seq, head_hash = head[0]["seq"], head[0]["hash"]
        at = utcnow().isoformat()
        body = {"seq": seq, "head": head_hash, "at": at}
        record: dict[str, Any] = {"seq": seq, "head_hash": head_hash, "methods": [],
                                  "detail": {"at": at}}
        if "signature" in self.methods:
            signer = self.p.signer_or_none()
            if signer is None:
                raise ValidationFailed("custody.anchor.methods names signature but no Ed25519 "
                                       "backend is installed")
            record["signature"] = signer.signature_block(djson.canonical(body).encode())
            record["methods"].append("signature")
        if "rfc3161" in self.methods:
            record["tsa_token"], record["detail"]["tsa"] = self._timestamp(head_hash)
            record["methods"].append("rfc3161")
        if "file" in self.methods:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({**body, "signature": record.get("signature")},
                                    sort_keys=True) + "\n")
            record["methods"].append("file")
            record["detail"]["file"] = str(self.path)
        with self.p.uow("system") as uow:
            row = uow.repo("anchors").add(record)
            if "event" in self.methods:
                record["methods"].append("event")
                uow.repo("anchors").update(row["id"], {"methods": record["methods"]})
            uow.audit("audit.anchored", principal_type="system", channel="scheduler",
                      detail={"seq": seq, "head": head_hash, "methods": record["methods"]})
            return uow.repo("anchors").require(row["id"])

    def _timestamp(self, head_hash: str) -> tuple[str | None, dict[str, Any]]:
        digest = bytes.fromhex(head_hash)
        req = timestamp_request(digest, secrets.randbits(63))
        try:
            with httpx.Client(transport=self.transport, timeout=20) as client:
                r = client.post(self.tsa_url, content=req,
                                headers={"Content-Type": "application/timestamp-query"})
            result = self._check_token(r.content, digest)
        except httpx.HTTPError as exc:
            return None, {"ok": False, "detail": f"TSA unreachable: {exc}"}
        return (base64.b64encode(r.content).decode() if result["ok"] else None), result

    def _check_token(self, raw: bytes, digest: bytes) -> dict[str, Any]:
        """Granted and the imprint matches; and, with a TSA CA configured, signed by it."""
        result = check_timestamp_response(raw, digest)
        if result["ok"] and self.tsa_ca:
            result = verify_tsa_signature(raw, digest, self.tsa_ca)
        return result

    def list(self, p: Principal) -> dict[str, Any]:
        self._admin(p)
        with self.p.uow() as uow:
            rows = uow.repo("anchors").list(order_by=["-seq"], limit=1000)
        signer = self.p.signer_or_none()
        return {"anchors": rows, "methods": self.methods, "file": str(self.path),
                "tsa_url": self.tsa_url or None, "tsa_ca_file": self.tsa_ca or None,
                "public_key": signer.public_key_b64 if signer else None,
                "key_id": signer.key_id if signer else None}

    def anchor_now(self, p: Principal) -> dict[str, Any] | None:
        self._admin(p)
        return self.anchor()

    def verify(self, p: Principal | None = None) -> dict[str, Any]:
        """Check every anchor against the live chain and its own evidence."""
        if p is not None:
            self._admin(p)
        from maya.core.crypto import verify as verify_signature
        with self.p.uow() as uow:
            anchors = uow.repo("anchors").list(order_by=["seq"])
            chain = uow.repo("audit_events").verify_chain()
            rows = {r["seq"]: r["hash"] for r in uow.repo("audit_events").list(
                seq__in=[a["seq"] for a in anchors])} if anchors else {}
        file_lines = self._file_lines()
        signer = self.p.signer_or_none()
        own_key = signer.public_key_b64 if signer else None
        results = []
        for a in anchors:
            live = rows.get(a["seq"])
            problems = []
            if live != a["head_hash"]:
                problems.append("the live chain no longer has this head at this position: "
                                "history before it was rewritten")
            sig = a["signature"] or {}
            body = djson.canonical({"seq": a["seq"], "head": a["head_hash"],
                                    "at": a["detail"].get("at")}).encode()
            if sig and not verify_signature(sig["public_key"], body, sig["signature"]):
                problems.append("the anchor's signature does not verify")
            elif sig and own_key and sig["public_key"] != own_key:
                problems.append("the anchor is signed by a key that is not this MAYA's")
            if "file" in a["methods"] and (a["seq"], a["head_hash"]) not in file_lines:
                problems.append("the anchor is missing from the append-only file")
            if a["tsa_token"]:
                tsa = self._check_token(base64.b64decode(a["tsa_token"]),
                                        bytes.fromhex(a["head_hash"]))
                if not tsa["ok"]:
                    problems.append(f"timestamp token: {tsa['detail']}")
            results.append({"seq": a["seq"], "head": a["head_hash"], "ok": not problems,
                            "problems": problems, "methods": a["methods"]})
        broken = [r for r in results if not r["ok"]]
        return {"ok": chain["ok"] and not broken, "chain": chain, "anchors": len(results),
                "broken": broken,
                "verdict": "chain and anchors agree" if chain["ok"] and not broken else
                "TAMPERING: " + ("the chain is broken" if not chain["ok"] else
                                 f"{len(broken)} anchor(s) contradict the chain")}

    def _file_lines(self) -> set[tuple[int, str]]:
        if not self.path.exists():
            return set()
        out = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                out.add((int(row["seq"]), row["head"]))
            except (ValueError, KeyError):
                continue
        return out
