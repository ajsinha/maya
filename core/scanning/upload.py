"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Looking at what arrived from outside, before it is trusted.

The requirement names five checks — malware, opcode analysis, dependency
vulnerabilities, secrets, licences — and the honest answer is different for each.
Three of them need something this platform deliberately does not ship. So the
port is defined, the platform reports whether one is wired, and where none is it
**says so rather than showing a tick**. That is the same stance taken about the
WORM backing and about toxicity metrics, and the consistency is the argument: a
governance platform that reports a clean scan because nothing looked is worse
than one that reports nothing, because the tick is what stops anybody asking.

| Check | What MAYA does |
|---|---|
| opcode analysis | **Answered by exclusion, which is stronger.** The artifact format vocabulary contains no `pickle`, so there is nothing to opcode-scan. A scanner deciding whether an opcode sequence is malicious is in an arms race; a format that cannot execute is not in one |
| secrets | **Done, offline, completely.** The same shapes the CI gate looks for, over the bytes that arrived |
| licences | **Done.** Declared licences against the firm's allow-list, which is a policy question and therefore configuration |
| malware | **A port.** No AV engine ships here and none is pretended |
| dependency vulnerabilities | **A port.** Needs an advisory feed, which needs egress this platform does not assume |

**Quarantine, not block.** A blocked upload is one somebody retries around — a
different filename, a different route, next week. A quarantined one is on the
record, attached to the thing it is about, with the reason a reviewer needs. The
material is kept and marked; nothing is silently discarded, because a scanner
that deletes its own evidence leaves nobody able to check whether it was right.

**A finding never quotes the secret it found.** A hit that carries the credential
is a second copy of it, in a table more people can read than the file it came
from.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger
from core.scanning.patterns import find as find_secrets

logger = get_logger(__name__)

#: What state a scanned upload lands in. `quarantined` is stored, marked and
#: unusable rather than absent — a scanner that deletes its own evidence leaves
#: nobody able to check whether it was right.
CLEAN, QUARANTINE = "clean", "quarantined"

#: The five checks, what each one is, and what this platform actually does.
CHECKS: Dict[str, Dict[str, str]] = {
    "secrets": {
        "state": "performed",
        "does": "looks for credential shapes in the bytes that arrived, using "
                "the same patterns the CI gate uses",
        "why": "an artifact carrying a private key is a credential leaving the "
               "institution inside something nobody thinks of as a document",
    },
    "licences": {
        "state": "performed",
        "does": "checks declared licences against the firm's allow-list",
        "why": "the list is a policy question and therefore configuration; "
               "shipping one would be this platform having an opinion about "
               "somebody else's legal position",
    },
    "opcode": {
        "state": "answered by exclusion",
        "does": "nothing, because the artifact format vocabulary contains no "
                "`pickle` and there is nothing to opcode-scan",
        "why": "a scanner deciding whether an opcode sequence is malicious is "
               "in an arms race; a format that cannot execute is not in one. "
               "Exclusion is the stronger answer and it was made earlier",
    },
    "malware": {
        "state": "port, unwired by default",
        "does": "calls whatever engine is configured, and reports that none is "
                "when none is",
        "why": "no AV engine ships here, and a clean result from nothing having "
               "looked is worse than no result — the tick is what stops "
               "anybody asking",
    },
    "dependencies": {
        "state": "port, unwired by default",
        "does": "calls whatever advisory source is configured",
        "why": "matching a manifest against known vulnerabilities needs a feed, "
               "which needs egress this platform does not assume",
    },
}

#: Licences a firm is likely to accept without a conversation. Configuration in
#: practice: this default is the permissive set, and the point of the check is
#: the ones that are NOT on it.
DEFAULT_LICENCES = ("MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0",
                    "ISC", "Unlicense", "CC0-1.0")

#: How much of an upload is read for credential shapes. A whole model artifact
#: can be gigabytes and a credential is not usually at the end of one — but the
#: bound is REPORTED, because a scan of the first slice presented as a scan is
#: the same lie as a scan by nothing at all.
MAX_BYTES = 8 * 1024 * 1024

#: What a declared licence looks like in a manifest. Several keys, because
#: nobody agrees, and looking under one of them is how a check quietly passes
#: everything.
LICENCE_KEYS = ("licence", "license", "spdx", "spdx_id", "licence_id")


class UploadScanner:
    """Scans an arriving artifact or document, and quarantines rather than blocks."""

    def __init__(self, *, malware=None, advisories=None,
                 licences: Sequence[str] = DEFAULT_LICENCES):
        # Ports. `None` means unwired, which is REPORTED — never treated as a
        # pass. Both take bytes and return a list of findings.
        self.malware, self.advisories = malware, advisories
        self.licences = frozenset(licences)

    # ---------------------------------------------------------------- scan
    def scan(self, content: bytes, *, filename: str = "",
             media_type: str = "", declared_licences: Optional[Sequence[str]] = None,
             manifest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Everything this platform can say about what just arrived."""
        findings: List[Dict[str, Any]] = []
        performed: List[str] = []
        unwired: List[str] = []

        read = content[:MAX_BYTES]
        truncated = len(content) > MAX_BYTES
        findings += self._secrets(read, filename)
        performed.append("secrets")

        findings += self._licences(declared_licences, manifest)
        performed.append("licences")

        malware, wired = self._port(self.malware, read, "malware")
        findings += malware
        (performed if wired else unwired).append("malware")

        deps, wired = self._port(self.advisories, manifest or {}, "dependencies")
        findings += deps
        (performed if wired else unwired).append("dependencies")

        state = QUARANTINE if findings else CLEAN
        return {
            "state": state, "findings": findings,
            "checks_performed": performed, "checks_unwired": unwired,
            "opcode_analysis": CHECKS["opcode"]["why"],
            "bytes_scanned": len(read), "truncated": truncated,
            "scanned_at": time.time(),
            "detail": self._detail(state, findings, unwired, truncated,
                                   len(content)),
        }

    # ------------------------------------------------------------- secrets
    @staticmethod
    def _secrets(content: bytes, filename: str) -> List[Dict[str, Any]]:
        """Credential shapes in the bytes that arrived.

        Decoded loosely on purpose: a credential inside a mostly-binary
        artifact is exactly the case worth catching, and refusing to look at
        anything that is not clean UTF-8 would skip it.
        """
        text = content.decode("utf-8", errors="ignore")
        return [{"check": "secrets", "severity": "high", **hit,
                 "where": filename or "the uploaded bytes",
                 # The match itself is never carried. A finding holding the
                 # credential is a second copy of it, in a table more people
                 # can read than the file it came from.
                 "why": (f"{hit['means']} appears in what was uploaded. The "
                         f"value is deliberately not recorded here")}
                for hit in find_secrets(text)]

    # ------------------------------------------------------------ licences
    def _licences(self, declared: Optional[Sequence[str]],
                  manifest: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        found = list(declared or ())
        for key in LICENCE_KEYS:
            value = (manifest or {}).get(key)
            if isinstance(value, str):
                found.append(value)
            elif isinstance(value, (list, tuple)):
                found.extend(str(v) for v in value)
        out = []
        for licence in {l.strip() for l in found if str(l).strip()}:
            if licence in self.licences:
                continue
            out.append({
                "check": "licences", "severity": "medium",
                "pattern": "licence not on the allow-list", "licence": licence,
                "why": (f"'{licence}' is not on this firm's allow-list. That is "
                        f"not a judgement about the licence — the list is "
                        f"configuration, because a platform with an opinion "
                        f"about somebody else's legal position is a platform "
                        f"nobody's counsel will accept"),
            })
        return out

    # ---------------------------------------------------------------- ports
    @staticmethod
    def _port(port, payload, name: str):
        """Call a configured engine, or report that none is.

        Never returns *clean* for an unwired port. A clean result from nothing
        having looked is worse than no result: the tick is what stops anybody
        asking.
        """
        if port is None:
            return [], False
        try:
            found = list(port(payload) or ())
        except Exception:
            # An engine that fell over must not pass the upload. Logged and
            # turned into a finding, because "the scanner was down" is a fact
            # about this upload that somebody has to decide about.
            logger.warning("the %s scanner raised; the upload is quarantined "
                           "rather than passed", name, exc_info=True)
            return [{"check": name, "severity": "high",
                     "pattern": "scanner failed",
                     "why": (f"the {name} scanner did not complete. An upload "
                             f"nothing could check is not an upload something "
                             f"checked and cleared")}], True
        return [{"check": name, "severity": "high", **f} for f in found], True

    # -------------------------------------------------------------- shaping
    @staticmethod
    def _detail(state, findings, unwired, truncated, total) -> str:
        if state == CLEAN:
            out = "nothing this platform can check found anything"
        else:
            kinds = sorted({f["check"] for f in findings})
            out = (f"quarantined: {len(findings)} finding(s) across "
                   f"{', '.join(kinds)}. Quarantined and not blocked — a "
                   f"blocked upload is one somebody retries around, and a "
                   f"quarantined one is on the record with the reason a "
                   f"reviewer needs")
        if unwired:
            out += (f". {', '.join(unwired)} could not be checked, because no "
                    f"engine is wired into this instance. That is reported "
                    f"rather than passed: a clean result from nothing having "
                    f"looked is worse than no result")
        if truncated:
            out += (f". Only the first {MAX_BYTES // (1024 * 1024)}MB of "
                    f"{total // (1024 * 1024)}MB were read for credential "
                    f"shapes — said out loud, because a scan of the first "
                    f"slice presented as a scan is the same lie as a scan by "
                    f"nothing at all")
        return out

    # ------------------------------------------------------------- posture
    def posture(self) -> Dict[str, Any]:
        """Which of the five checks this instance can actually perform."""
        rows = []
        for name, spec in CHECKS.items():
            wired = (spec["state"] == "performed"
                     or (name == "malware" and self.malware is not None)
                     or (name == "dependencies" and self.advisories is not None))
            rows.append({"check": name, **spec, "available": wired})
        unavailable: List[str] = [str(r["check"]) for r in rows
                                  if not r["available"]
                                  and r["state"] != "answered by exclusion"]
        return {
            "checks": rows, "unavailable": unavailable,
            "allowed_licences": sorted(self.licences),
            "detail": (
                f"{len([r for r in rows if r['available']])} of {len(rows)} "
                f"checks are available on this instance"
                + (f". {', '.join(unavailable)} need an engine nothing has "
                   f"wired in, and are reported as unavailable rather than as "
                   f"clean — the tick is what stops anybody asking"
                   if unavailable else "")
                + ". Opcode analysis is answered by exclusion: the format "
                  "vocabulary contains no `pickle`, so there is nothing to "
                  "scan, and a format that cannot execute beats a scanner that "
                  "has to decide whether an opcode sequence is malicious"),
        }
