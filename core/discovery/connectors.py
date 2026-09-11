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
SAGEMAKER, VERTEX, SAS, CMDB = "sagemaker", "vertex", "sas", "cmdb"

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
    SAGEMAKER: {
        "reads": "a SageMaker Model Registry export — the JSON "
                 "`list-model-packages` and `describe-model-package` produce, "
                 "by package group",
        "produced_by": "a scheduled job in the AWS account that owns the "
                       "registry, with that account's own role",
        "why_not_the_api": "cross-account read into every ML account in the "
                           "bank is a standing trust relationship, and a "
                           "governance register is the worst place to hold "
                           "one. An approval status in SageMaker is also not "
                           "an approval in the bank's sense, and reading it "
                           "live would invite exactly that confusion",
    },
    VERTEX: {
        "reads": "a Vertex AI Model Registry export — the JSON "
                 "`gcloud ai models list` produces, with version aliases",
        "produced_by": "a scheduled job in the project that owns the models",
        "why_not_the_api": "the same standing-credential objection, per "
                           "project. Vertex also scopes models by region, so a "
                           "live reader would silently see one region's estate "
                           "and report it as the estate",
    },
    SAS: {
        "reads": "a SAS metadata extract — the model manager inventory, or the "
                 "`_metadata` tables a SAS 9 platform exposes",
        "produced_by": "a SAS administrator, from the metadata server",
        "why_not_the_api": "there is frequently no API worth the name, and the "
                           "estate this reaches is the one that matters most: "
                           "a bank's oldest credit and capital models live "
                           "here, they were never in an ML platform, and they "
                           "are the models a supervisor asks about first",
    },
    CMDB: {
        "reads": "a configuration-management extract — CIs of a model or "
                 "analytics class, with their owners and the service they "
                 "support",
        "produced_by": "a scheduled report from the CMDB, which somebody in "
                       "IT service management already owns",
        "why_not_the_api": "a CMDB is the one source here that holds something "
                           "governance genuinely wants — the **service** a "
                           "thing supports, which is the nearest thing anybody "
                           "has to materiality — and it is also the source "
                           "most likely to be stale. Reading it on a schedule "
                           "makes the staleness visible; reading it live would "
                           "make it invisible",
    },
}

#: Fields a source carries that LOOK like governance facts and are not. Naming
#: them is the point: `must_still_be_established` protects against an absence,
#: and an absence is the easy case — somebody notices. The hard case is a
#: present field with the right word on it, because nobody goes looking for the
#: difference between two things called "approved".
LOOKS_LIKE_BUT_IS_NOT: Dict[str, Tuple[Tuple[str, str], ...]] = {
    SAGEMAKER: ((
        "sagemaker_approval_status",
        "`Approved` in SageMaker means a pipeline step passed. Approval here "
        "means a named person accepted a model at a tier that decided how many "
        "signatures it needed. Reading one as the other gives the register a "
        "column of approvals nobody gave"),),
    MLFLOW: ((
        "stage",
        "`Production` is a deployment stage, not an authorisation. A model can "
        "sit in Production having been promoted by whoever had the button"),
        ("mlflow_user",
         "whoever last pushed, which is not an accountable owner. The register "
         "means a named individual who answers for the model, and an ML "
         "platform has no field for that because it is not its question")),
    CMDB: ((
        "business_service",
        "the nearest thing in the bank to materiality, and still not "
        "materiality. It tells a triager where to go and ask, which is worth a "
        "great deal and is not an answer"),),
    UNITY: ((
        "catalog_owner",
        "a catalogue grant, which is who may read the object rather than who "
        "answers for the model"),),
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
                f"the connectors are {', '.join(SOURCES)} — each reads a "
                f"document "
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
        misread = sum(len(c["do_not_read_as"]) for c in rows)
        if misread:
            out += (f". {misread} field(s) across these candidates carry a "
                    f"governance-sounding name and do not mean what it says — "
                    f"each is listed under `do_not_read_as` with the "
                    f"difference, because an absent fact is the easy case and "
                    f"a present one with the right word on it is not")
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

    def _read_sagemaker(self, document: Any) -> List[Dict[str, Any]]:
        """SageMaker model packages, by group.

        `ModelApprovalStatus` is read and carried as evidence, and it is
        deliberately **not** mapped onto anything in the register. `Approved`
        in SageMaker means a pipeline step passed; approval here means a named
        person accepted a model at a tier that decided how many signatures it
        needed. Treating them as the same field is how an inventory acquires a
        column of approvals nobody gave.
        """
        payload = _as_json(document)
        groups = payload.get("ModelPackageSummaryList") \
            or payload.get("model_packages") \
            or (payload if isinstance(payload, list) else [])
        out = []
        for entry in groups:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("ModelPackageGroupName")
                       or entry.get("ModelPackageName") or "").strip()
            if not name:
                continue
            arn = str(entry.get("ModelPackageArn") or "").strip()
            containers = entry.get("InferenceSpecification", {}).get(
                "Containers") or []
            digest = ""
            for container in containers:
                if isinstance(container, dict) and container.get("ImageDigest"):
                    digest = str(container["ImageDigest"])
                    break
            out.append(self._candidate(
                SAGEMAKER, name,
                location=arn or f"sagemaker://model-packages/{name}",
                digest=digest,
                evidence={
                    "artifact_digest": digest or None,
                    "version": entry.get("ModelPackageVersion"),
                    # Carried, never mapped. See the docstring.
                    "sagemaker_approval_status": entry.get(
                        "ModelApprovalStatus"),
                    "created_at": entry.get("CreationTime"),
                    "description": entry.get("ModelPackageDescription"),
                }))
        return out

    def _read_vertex(self, document: Any) -> List[Dict[str, Any]]:
        """Vertex AI models.

        The **region** is carried on every candidate rather than dropped,
        because a Vertex estate is regional and an export that covered one
        region looks exactly like an export that covered all of them. A
        candidate that did not say which region it came from would let an
        incomplete sweep read as a complete one.
        """
        payload = _as_json(document)
        rows = payload.get("models") or (payload if isinstance(payload, list)
                                         else [])
        out = []
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("displayName") or entry.get("display_name")
                       or entry.get("name") or "").strip()
            if not name:
                continue
            resource = str(entry.get("name") or "").strip()
            region = ""
            if "/locations/" in resource:
                region = resource.split("/locations/", 1)[1].split("/", 1)[0]
            out.append(self._candidate(
                VERTEX, name,
                location=resource or f"vertex://models/{name}",
                digest=str(entry.get("artifactUri") or "").strip(),
                evidence={
                    "artifact_digest": entry.get("artifactUri"),
                    "region": region or None,
                    "version_id": entry.get("versionId")
                    or entry.get("version_id"),
                    "aliases": entry.get("versionAliases")
                    or entry.get("version_aliases"),
                    "labels": entry.get("labels"),
                }))
        return out

    def _read_sas(self, document: Any) -> List[Dict[str, Any]]:
        """A SAS metadata extract.

        The estate this reaches is the one that matters most and the one an ML
        connector never sees: a bank's oldest credit, capital and ALM models,
        built before anybody used the word platform, and the first thing a
        supervisor asks about. There is usually no digest, so confidence sits
        at the lower band and the triage does more work — which is correct,
        because a SAS metadata row is a much weaker claim that something is a
        model than an entry in a model registry is.
        """
        payload = _as_json(document)
        rows = payload.get("models") or payload.get("entries") \
            or (payload if isinstance(payload, list) else [])
        out = []
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or entry.get("Name") or "").strip()
            if not name:
                continue
            folder = str(entry.get("folder") or entry.get("library")
                         or "").strip()
            out.append(self._candidate(
                SAS, f"{folder}/{name}" if folder else name,
                location=f"sas://{folder}/{name}" if folder
                else f"sas://{name}",
                digest="",
                evidence={
                    "artifact_digest": None,
                    "folder": folder or None,
                    "sas_type": entry.get("type") or entry.get("Type"),
                    "modified_at": entry.get("modified")
                    or entry.get("MetadataUpdated"),
                    "modified_by": entry.get("modifiedBy"),
                    "project": entry.get("project"),
                }))
        return out

    def _read_cmdb(self, document: Any) -> List[Dict[str, Any]]:
        """Configuration items of a model or analytics class.

        The one source here that holds something governance genuinely wants:
        the **business service** a thing supports, which is the nearest thing
        any system in the bank has to materiality. It is carried as evidence
        and it is still not materiality — a service name tells a triager where
        to go and ask, which is worth a great deal and is not the same as an
        answer.

        It is also the source most likely to be stale, so `last_reviewed` is
        carried when the extract has it. A CI nobody has looked at in three
        years is a different candidate from one reviewed last month, and the
        difference belongs in front of whoever triages it.
        """
        payload = _as_json(document)
        rows = payload.get("items") or payload.get("cis") \
            or (payload if isinstance(payload, list) else [])
        out = []
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or entry.get("ci_name") or "").strip()
            if not name:
                continue
            out.append(self._candidate(
                CMDB, name,
                location=str(entry.get("sys_id") or entry.get("id")
                             or f"cmdb://{name}"),
                digest="",
                evidence={
                    "artifact_digest": None,
                    "ci_class": entry.get("ci_class") or entry.get("class"),
                    "business_service": entry.get("business_service")
                    or entry.get("service"),
                    "support_group": entry.get("support_group"),
                    "assigned_to": entry.get("assigned_to"),
                    "environment": entry.get("environment"),
                    "last_reviewed": entry.get("last_reviewed")
                    or entry.get("sys_updated_on"),
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
            # Only for fields this candidate actually carries: a warning about
            # something that is not there is noise, and noise is how a reader
            # learns to skip the section that matters.
            "do_not_read_as": [
                {"field": field, "why": why}
                for field, why in LOOKS_LIKE_BUT_IS_NOT.get(source, ())
                if evidence.get(field) is not None],
        }

    # ------------------------------------------------------------------ what
    @staticmethod
    def describe() -> Dict[str, Any]:
        """What each connector reads, and what no connector can bring."""
        return {
            "sources": [
                {"source": k, **v,
                 "do_not_read_as": [{"field": f, "why": w}
                                    for f, w in LOOKS_LIKE_BUT_IS_NOT.get(k, ())]}
                for k, v in SOURCES.items()],
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
