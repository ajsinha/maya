"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reading what an ML platform already knows, and the two things this must not do.

Most of a bank's models are already in something --- an MLflow registry, a Unity
Catalog, a directory of repositories. Making somebody retype them is how an
inventory stays incomplete, and completeness is the precondition for every other
control here. So there are connectors.

**The first thing they must not do is register a model.** An import that created
model records would produce a register full of models with no tier, no
accountable individual, no approved use and no independent challenge --- an
inventory of everything, which is the failure `core/lifecycle/intake.py` exists
to prevent and which no amount of subsequent tidying reverses. A connector
produces **candidates**. Somebody triages them, and the triage may well say *this
is not a model*.

**The second is hold credentials.** A governance platform with read access to
every ML platform in the bank is a large new attack surface for a read-only
need, and it puts the register on the availability path of four systems it does
not operate. So a connector parses **a document the source system produces** ---
an MLflow registry export, a catalogue listing, a repository manifest. The
export is somebody's scheduled job; the parsing is here. That boundary is the
same one the platform draws everywhere else, and it has the same shape as
refusing to fetch an artifact's logs.

**What comes across is the smaller half, and the report says so.** An ML
platform knows the run, the metrics, the artifact digest and the lineage. It
does not know materiality, approved use, the accountable individual, or whether
anybody challenged the thing --- because those are not facts about a model, they
are facts about an institution's relationship to it. So every candidate carries
two lists: what was read, and **what must still be established**. The second is
always longer, and a connector that hid that would be selling an import as a
migration.

**And the fingerprint has to outlive the source.** Keying a candidate on an
MLflow `run_id` means a re-registration in MLflow arrives as a new candidate and
the triage somebody already did is lost. The key is the artifact digest where
there is one and a normalised name where there is not, which survives the source
being reorganised --- the same reasoning the discovery register already applies
to a file that moves.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Sequence, Tuple

from core.discovery.common import DiscoveryError
from core.log import get_logger

logger = get_logger(__name__)

MLFLOW, UNITY, GIT = "mlflow", "unity_catalog", "git"

#: What each connector reads, and what a firm has to produce for it. Named so
#: the operational dependency is visible before anybody wires one: this is a
#: scheduled export somebody owns, not a live integration.
SOURCES: Dict[str, Dict[str, str]] = {
    MLFLOW: {
        "reads": "an MLflow model-registry export — the JSON `mlflow models "
                 "search` and `mlflow registered-models list` produce",
        "produced_by": "a scheduled job in the ML platform, run with the "
                       "platform's own credentials",
        "why_not_the_api": "a governance register holding credentials to every "
                           "ML platform in the bank is a large attack surface "
                           "for a read-only need, and it puts this platform on "
                           "the availability path of one it does not operate",
    },
    UNITY: {
        "reads": "a Unity Catalog listing — the rows of "
                 "`system.information_schema` for models and their owners",
        "produced_by": "a scheduled query, exported as JSON or CSV",
        "why_not_the_api": "the same reason, plus a catalogue query is cheap to "
                           "schedule and expensive to hold a token for",
    },
    GIT: {
        "reads": "a repository manifest — paths, latest commit, and any "
                 "declared model metadata found at those paths",
        "produced_by": "a crawl run where the repositories are, by whoever "
                       "already has read access to them",
        "why_not_the_api": "MAYA does not clone repositories. A register that "
                           "pulled source would be holding somebody's code as "
                           "well as claims about it",
    },
}

#: What governance needs that an ML platform does not have. Published, because
#: the gap is the finding: an import is not a migration, and the difference is
#: exactly this list.
NOT_IN_THE_SOURCE: Tuple[Tuple[str, str], ...] = (
    ("materiality", "what rides on this model. No ML platform records it, "
                    "because it is a fact about the business and not about the "
                    "artifact"),
    ("accountable_owner", "a named individual, not a team and not a service "
                          "account. An MLflow owner is whoever last pushed"),
    ("approved_use", "what this model is authorised FOR. A registry knows it "
                     "exists, not what anybody may do with it"),
    ("independent_challenge", "whether somebody other than the builder looked. "
                              "Nothing in an ML platform can answer this and "
                              "nothing should be read as if it did"),
    ("limitations", "what the model cannot do, stated by the people who know"),
)


class Connectors:
    """Parses what a source system exported, and produces candidates only."""

    def __init__(self, discovery, registry=None):
        self.discovery, self.registry = discovery, registry

    # ------------------------------------------------------------------ read
    def read(self, source: str, document: Any) -> Dict[str, Any]:
        """Parse an export into candidates. Nothing is written."""
        if source not in SOURCES:
            raise DiscoveryError(
                "unknown_source", f"'{source}' is not a connector",
                f"the three are {', '.join(SOURCES)} — each reads a document "
                f"the source system exports, because MAYA holds credentials to "
                f"none of them")
        rows = getattr(self, f"_read_{source}")(document)
        known = self._already_registered(rows)
        return {
            "source": source, "candidates": rows, "count": len(rows),
            "already_registered": known,
            "not_in_the_source": [{"field": f, "why": w}
                                  for f, w in NOT_IN_THE_SOURCE],
            "registers_anything": False,
            "detail": self._detail(source, rows, known),
        }

    def _detail(self, source: str, rows: List[Dict[str, Any]],
                known: List[str]) -> str:
        if not rows:
            return (f"this {source} export names no model. Worth checking the "
                    f"export rather than concluding the platform is empty: a "
                    f"connector reads what was written out, and a job that ran "
                    f"and produced nothing looks identical here to one that "
                    f"did not run")
        out = (f"{len(rows)} candidate(s) read from a {source} export. **None "
               f"of them is a registered model and none will be** — a "
               f"connector produces candidates and somebody triages them, "
               f"because an import that created records would produce a "
               f"register full of models with no tier, no accountable "
               f"individual and no approved use")
        if known:
            out += (f". {len(known)} already correspond to something in the "
                    f"register and are reported so the triage can be a "
                    f"reconciliation rather than a duplicate")
        out += (f". {len(NOT_IN_THE_SOURCE)} governance facts are not in this "
                f"export and cannot be — materiality, an accountable "
                f"individual, an approved use, independent challenge and "
                f"limitations are facts about an institution's relationship to "
                f"a model rather than about the model, and no ML platform holds "
                f"them")
        return out

    def _already_registered(self, rows: Sequence[Dict[str, Any]]) -> List[str]:
        if self.registry is None:
            return []
        digests = set()
        for model in self.registry.list():
            for version in self.registry.versions(model["urn"]):
                if version.get("artifact_digest"):
                    digests.add(version["artifact_digest"])
        return sorted({r["location"] for r in rows
                       if (r.get("evidence") or {}).get("artifact_digest")
                       in digests})

    # --------------------------------------------------------------- ingest
    def ingest(self, source: str, document: Any, *,
               actor: str = "system") -> Dict[str, Any]:
        """Parse and hand the candidates to the discovery register.

        Which is where they stay until somebody triages them. The register
        already deduplicates on the fingerprint and already measures the
        precision of whatever produced them, so a connector is graded exactly
        like a scanner — and a connector nobody grades is one nobody should
        point at a second platform.
        """
        read = self.read(source, document)
        out = self.discovery.ingest(f"connector:{source}", read["candidates"],
                                    actor=actor)
        logger.info("connector %s produced %d candidate(s)", source,
                    read["count"])
        return {**read, "ingested": out,
                "detail": read["detail"] + ". " + out.get("detail", "")}

    # -------------------------------------------------------------- parsers
    def _read_mlflow(self, document: Any) -> List[Dict[str, Any]]:
        """MLflow registered models. Tolerant of the two shapes it exports in."""
        payload = _as_json(document)
        models = payload.get("registered_models") or payload.get("models") \
            or (payload if isinstance(payload, list) else [])
        out = []
        for entry in models:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            versions = entry.get("latest_versions") or entry.get("versions") or []
            newest = versions[-1] if versions else {}
            digest = str(newest.get("source_digest")
                         or newest.get("run_id") or "").strip()
            out.append(self._candidate(
                MLFLOW, name,
                location=f"mlflow://models/{name}",
                digest=digest,
                evidence={
                    "artifact_digest": digest or None,
                    "latest_version": newest.get("version"),
                    "stage": newest.get("current_stage"),
                    "mlflow_user": entry.get("user_id")
                    or newest.get("user_id"),
                    "description": entry.get("description"),
                    "tags": entry.get("tags"),
                }))
        return out

    def _read_unity_catalog(self, document: Any) -> List[Dict[str, Any]]:
        payload = _as_json(document)
        rows = payload.get("rows") or (payload if isinstance(payload, list)
                                       else [])
        out = []
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            full = ".".join(str(entry.get(k) or "").strip()
                            for k in ("catalog_name", "schema_name",
                                      "model_name") if entry.get(k))
            if not full:
                continue
            out.append(self._candidate(
                UNITY, full,
                location=f"unity://{full}",
                digest="",
                evidence={
                    "artifact_digest": None,
                    "catalog_owner": entry.get("model_owner")
                    or entry.get("owner"),
                    "created_at": entry.get("created_at"),
                    "comment": entry.get("comment"),
                }))
        return out

    def _read_git(self, document: Any) -> List[Dict[str, Any]]:
        payload = _as_json(document)
        entries = payload.get("paths") or payload.get("files") \
            or (payload if isinstance(payload, list) else [])
        out = []
        for entry in entries:
            path = entry if isinstance(entry, str) else str(
                entry.get("path") or "")
            if not path.strip():
                continue
            meta = entry if isinstance(entry, dict) else {}
            out.append(self._candidate(
                GIT, path,
                location=f"git://{meta.get('repository', 'repo')}/{path}",
                digest=str(meta.get("blob_sha") or ""),
                evidence={
                    "artifact_digest": meta.get("blob_sha"),
                    "repository": meta.get("repository"),
                    "last_commit": meta.get("commit"),
                    "last_author": meta.get("author"),
                }))
        return out

    @staticmethod
    def _candidate(source: str, name: str, *, location: str, digest: str,
                   evidence: Dict[str, Any]) -> Dict[str, Any]:
        """One candidate, keyed on something that outlives the source.

        The artifact digest where there is one, and a normalised name where
        there is not. An MLflow `run_id` would key a candidate to a row that a
        re-registration replaces, and the triage somebody already did would be
        lost — the same reasoning the register applies to a file that moves.
        """
        basis = digest or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        fingerprint = hashlib.sha256(
            f"{source}|{basis}".encode("utf-8")).hexdigest()
        return {
            "source": source, "location": location,
            "fingerprint": f"sha256:{fingerprint}",
            "proposed_as": "model",
            # Deliberately not 1.0. A connector found a row in a registry, which
            # is evidence that somebody built something and not evidence that it
            # is a model — that determination is triage's, and a confidence of
            # one would be the connector making it.
            "confidence": 0.6 if digest else 0.4,
            "evidence": {k: v for k, v in evidence.items() if v is not None},
            "must_still_be_established": [f for f, _ in NOT_IN_THE_SOURCE],
        }

    # ------------------------------------------------------------------ what
    @staticmethod
    def describe() -> Dict[str, Any]:
        """What each connector reads, and what no connector can bring."""
        return {
            "sources": [{"source": k, **v} for k, v in SOURCES.items()],
            "not_in_the_source": [{"field": f, "why": w}
                                  for f, w in NOT_IN_THE_SOURCE],
            "registers_anything": False, "holds_credentials": False,
            "detail": ("a connector parses a document the source system "
                       "exported and produces candidates for triage. It does "
                       "not register models — an import that did would produce "
                       "an inventory of everything — and it does not hold "
                       "credentials, because read access to every ML platform "
                       "in the bank is a large attack surface for a read-only "
                       "need"),
        }


def _as_json(document: Any) -> Any:
    if isinstance(document, (dict, list)):
        return document
    if isinstance(document, bytes):
        document = document.decode("utf-8")
    try:
        return json.loads(document)
    except (TypeError, ValueError) as exc:
        logger.warning("connector export is not JSON: %s", exc)
        raise DiscoveryError(
            "unreadable_export",
            f"this export is not JSON: {exc}",
            "export it as JSON. A connector parses a document the source "
            "system produced, so a malformed one is a job to fix over there "
            "rather than something to guess at here") from exc
