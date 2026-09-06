"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Model versions: immutable, digested, and classified on arrival.

A version is created once and never edited. That is not fastidiousness — it is
what makes a manifest digest worth computing, and what lets a warrant descriptor
name a version and mean something six months later.

The trainability class is DERIVED here rather than declared. Asking an owner to
self-report "is this trained?" invites the answer that requires least work; the
class falls out of how the parameter object is inhabited, which is a fact about
the artifact instead of an opinion about it.
"""
from __future__ import annotations

import logging

import time
from typing import Any, Dict, List, Optional

from core.artifacts import is_content_address
from core.domain import (FitProcedure, OutputKind, ParameterKind, ParameterObject,
                         ParametricKernel)
from core.evidence import EvidenceEngine
from core.ports import LifecycleGate
from core.registry.catalogue import ModelCatalogue
from core.registry.common import RegistryError
from core.registry.specs import schema_of
from db import VersionRepository
from db.database import digest as canonical_digest
from core.log import get_logger, swallowed

logger = get_logger(__name__)


def _one_of(enum, value: Any, field: str):
    """Convert to an enum member, or refuse naming the field and the choices.

    Every vocabulary here is small and closed, so the useful refusal is the one
    that lists it. `ValueError: 'not_a_kind' is not a valid ParameterKind` names
    the Python class rather than the field somebody typed into.
    """
    try:
        return enum(value)
    except ValueError as exc:
        allowed = ", ".join(m.value for m in enum)
        swallowed(logger, exc, f"converted '{value}' to a {field}",
                  detail="translated into a refusal that names the field and "
                         "the vocabulary; the bare ValueError reached the "
                         "caller as a 500 with an empty body",
                  level=logging.INFO)
        raise RegistryError(
            f"'{value}' is not a {field}; expected one of {allowed}",
        ) from exc


def semver_key(semver: str):
    """A sortable key for a version string, numeric parts compared as numbers.

    `"1.10.0"` must sort above `"1.9.0"`, which string comparison gets wrong,
    and `"2.0.0"` above `"1.0.1"` however recently the hotfix was cut.

    Anything unparseable sorts below everything parseable rather than raising:
    a version somebody named `"draft"` is not a reason to refuse to answer which
    version is latest, and putting it last would let it silently become the
    answer.
    """
    parts = []
    for chunk in str(semver or "").split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else -1)
    return tuple(parts) or (-1,)


def latest_version(rows):
    """The highest-numbered version, or None.

    `VersionRepository.ORDER` is `created_at`, so `rows[-1]` is the most
    recently *created* version — which is not the latest one. Cut `2.0.0`, then
    hotfix `1.0.1` against the old line, and `rows[-1]` is the hotfix: the
    composition type check would then compare schemas against `1.0.1`, and a
    risk assessment would read its trainability class, while everybody involved
    believes the answer is about `2.0.0`.

    Ten call sites took `rows[-1]`. This is what they all meant, written once —
    because ten copies of "the latest version" is ten chances for one of them to
    mean something else.

    Order of creation still breaks a tie, so two rows sharing a version number
    resolve to the later one rather than to whichever the database returned
    first.
    """
    if not rows:
        return None
    return max(rows, key=lambda r: (semver_key(r.get("semver")),
                                    r.get("created_at") or 0))


class VersionService:
    """Creates and approves immutable model versions."""

    def __init__(self, versions: VersionRepository, catalogue: ModelCatalogue,
                 evidence: EvidenceEngine, gate: Optional[LifecycleGate] = None):
        self.versions, self.catalogue, self.evidence = versions, catalogue, evidence
        self.gate = gate
        self.policy = None
        # Set at wiring time, like `policy` and `artifacts`. It answers the
        # governance facts this service does not hold — open findings,
        # validations, documents — so a gate is judged on what is true rather
        # than on what a default says.
        self.facts = None
        # Set at wiring time. When present, a digest naming bytes MAYA holds is
        # resolved here rather than taken on faith, and its size and address go
        # onto the version so a warrant can state them.
        self.artifacts = None

    @staticmethod
    def kernel_of(spec: Dict[str, Any], artifact_digest: Optional[str]) -> ParametricKernel:
        """The kernel a spec describes, or a refusal naming the word.

        `ParameterKind("not_a_kind")` raises a bare `ValueError`, which reached
        the caller as a 500 with an empty body — no code, no remediation, and
        nothing saying which of the three enum fields was wrong. A typo in a
        vocabulary is the most ordinary mistake there is here, and it was the
        one refusal in the register that told you nothing.
        """
        return ParametricKernel(
            parameters=ParameterObject(
                _one_of(ParameterKind, spec.get("parameter_kind", "none"),
                        "parameter_kind"), artifact_digest),
            input_schema=schema_of(spec.get("input_schema", [])),
            output_schema=schema_of(spec.get("output_schema", [])),
            output_kind=_one_of(OutputKind, spec.get("output_kind", "point_estimate"),
                                "output_kind"),
            deterministic=bool(spec.get("deterministic", True)),
            fit=_one_of(FitProcedure, spec.get("fit_procedure", "none"),
                        "fit_procedure"),
            adaptive=bool(spec.get("adaptive", False)))

    @staticmethod
    def _refuse_unexplained_parameters(kernel: ParametricKernel) -> None:
        """`P` is inhabited and nothing is declared to have inhabited it.

        This was silently permitted, and it failed in the permissive direction,
        which is the direction that costs something. `trainability_class` ends
        with `_FIT_TO_CLASS.get(self.fit, "T0")`, and the only key absent from
        that map is `NONE` — so a kernel with real, inspectable parameters and
        no declared fit procedure came back **T0**. T0 means `P` is *terminal*:
        no parameters at all. `requires_fitting_evidence` reads the class, so
        the model was then exempted from fitting evidence on the grounds that it
        has no parameters to have fitted, while carrying a set of them.

        The two declarations contradict each other. Every legitimate way `P`
        gets inhabited has a procedure — hand-set weights are `author` or
        `elicit`, a foundation model is `configure`, a fit is `estimate` or
        `train`. `none` genuinely means `P` is empty, which is exactly what
        `is_terminal` already says. So this is refused at declaration rather
        than resolved, because a state nothing can reach needs no downstream
        check, and the permissive resolution is one nobody would have noticed.

        Opaque is untouched: `P` is inhabited there too, but inaccessibly, and
        that is T6 — a real class with its own consequences, reached before this
        question is asked.
        """
        if (kernel.parameters.is_accessible
                and not kernel.parameters.is_terminal
                and kernel.fit is FitProcedure.NONE):
            raise RegistryError(
                f"this version declares parameters "
                f"('{kernel.parameters.kind.value}') and no fit procedure, which "
                f"says both that the model has parameters and that nothing "
                f"produced them. Declare how P was inhabited — 'calibrate', "
                f"'estimate', 'train', 'configure', 'elicit' or 'author' — or "
                f"declare parameter_kind 'none' if there really are none")

    #: Everything a kernel spec may say. Read off the code that consumes one:
    #: `kernel_of` and the schemas here, and the realisation keys the execution
    #: grammar reads from it.
    KERNEL_KEYS = frozenset({
        "parameter_kind", "fit_procedure", "output_kind", "adaptive",
        "deterministic", "input_schema", "output_schema",
        "artifact_format", "runtime", "entry", "environment", "seed",
        "descriptor_only",
    })

    @classmethod
    def _refuse_unknown_kernel_keys(cls, kernel_spec: Dict[str, Any]) -> None:
        """A key nobody reads is a key the caller believes is doing something.

        `kernel` is a free-form dict, so a developer who put `artifact_digest`
        inside it — beside `runtime`, `entry` and the schemas, which is exactly
        where it looks like it belongs — got a 201 and a `descriptor_only`
        version with no artifact bound to it. Nothing was wrong with the
        request, nothing was said, and the version was not the version they
        thought they had made.
        """
        unknown = sorted(set(kernel_spec) - cls.KERNEL_KEYS)
        if unknown:
            raise RegistryError(
                f"the kernel declares {', '.join(unknown)}, which nothing reads. "
                f"A kernel says what the model IS: {', '.join(sorted(cls.KERNEL_KEYS))}. "
                f"`artifact_digest` and `artifact_uri` are arguments of their "
                f"own rather than kernel keys, because the bytes are not part "
                f"of the kernel's type")

    def create(self, urn: str, semver: str, kernel_spec: Dict[str, Any],
               contract_spec: Optional[Dict[str, Any]] = None,
               artifact_digest: Optional[str] = None,
               artifact_uri: Optional[str] = None,
               actor: str = "system") -> Dict[str, Any]:
        m = self.catalogue.require(urn)
        # A new version IS a change to the model. Adding one to an attested
        # record without an amendment is how the record quietly stops describing
        # what runs.
        self._check_open(m)
        if self.versions.one(model_id=m["id"], semver=semver):
            raise RegistryError(
                f"version {semver} already exists for {urn}; versions are immutable")

        self._refuse_unknown_kernel_keys(kernel_spec)

        # A digest is a content address or it is not recorded.
        #
        # This accepted whatever string arrived. `sha256:not-a-digest-at-all`
        # went onto a version with a 201, and the screen above it says "a
        # location with no digest cannot be checked" — which was true, and so
        # was the case it did not mention. The store refuses a malformed address
        # when it goes looking for the bytes, so the only versions where this
        # was never noticed are exactly the ones whose artifact lives in
        # somebody else's engine: the T6 vendor models, where the digest is the
        # entire control.
        if artifact_digest and not is_content_address(artifact_digest):
            raise RegistryError(
                f"'{artifact_digest}' is not a content address; a digest looks "
                f"like 'sha256:' followed by 64 hexadecimal characters. Leave "
                f"it out if the bytes are not yet digested — a version with no "
                f"digest is honest, and one carrying a digest nothing can "
                f"resolve is not")

        artifact_size = None
        held = self._held(artifact_digest)
        if held is not None:
            # The store is the authority on its own contents. A caller may name
            # the digest and leave the URI to us; a caller who names both and
            # gets the URI wrong is corrected rather than believed.
            artifact_uri = held["uri"]
            artifact_size = held["size"]
            if not kernel_spec.get("artifact_format"):
                kernel_spec = dict(kernel_spec, artifact_format=held["format"])

        kernel = self.kernel_of(kernel_spec, artifact_digest)
        self._refuse_unexplained_parameters(kernel)
        manifest = {"urn": urn, "semver": semver, "kernel": kernel_spec,
                    "contract": contract_spec or {},
                    "artifact_digest": artifact_digest, "artifact_uri": artifact_uri,
                    "artifact_size": artifact_size}
        row = {"model_id": m["id"], "semver": semver, "manifest": manifest,
               "manifest_digest": canonical_digest(manifest),
               "trainability_class": kernel.trainability_class,
               "parameter_kind": kernel.parameters.kind.value,
               "fit_procedure": kernel.fit.value, "deterministic": kernel.deterministic,
               "input_schema": kernel_spec.get("input_schema", []),
               "output_schema": kernel_spec.get("output_schema", []),
               "contract": contract_spec or {}, "artifact_digest": artifact_digest,
               "artifact_uri": artifact_uri, "artifact_size": artifact_size,
               "status": "draft", "created_at": time.time(), "created_by": actor}
        # Both writes together, or neither.
        #
        # These were two separate commits, and the gap between them is not
        # theoretical: `version_created` is the node segregation of duties is
        # decided from. A crash after the row and before the node leaves a
        # version that exists with no record of who created it — and the rule
        # "the person who created a version may not approve it" then has nothing
        # to read, so it permits everything. The control does not fail closed;
        # it fails silent.
        #
        # `db.transaction()` is re-entrant, and its docstring names this exact
        # use: a service wraps a whole governance act without knowing what its
        # collaborators do.
        with self.versions.db.transaction():
            self.versions.add(row)
            self.evidence.append(
                "version_created", "version", row["id"],
                {"semver": semver, "digest": row["manifest_digest"],
                 "trainability_class": row["trainability_class"]}, actor=actor)
        return row

    def _held(self, digest: Optional[str]) -> Optional[Dict[str, Any]]:
        """What MAYA holds under this digest, or None if it holds nothing.

        A digest MAYA cannot resolve is not an error: plenty of artifacts live
        in a model store somewhere else and are named here so the engine can
        check them on load. The distinction is recorded rather than enforced,
        and the warrant carries it as `held_by_maya`.
        """
        if not digest or self.artifacts is None:
            return None
        try:
            return self.artifacts.describe(digest)
        except Exception as exc:                       # any store failure at all
            logger.info("artifact %s not resolvable in the store: %s", digest, exc)
            return None

    def _check_open(self, model: Dict[str, Any]) -> None:
        if self.gate is None:
            return
        allowed, why = self.gate.may_mutate(model["id"])
        if not allowed:
            raise RegistryError(f"cannot add a version to {model['urn']}: {why}")

    def list(self, urn: str) -> List[Dict[str, Any]]:
        return self.versions.many(model_id=self.catalogue.require(urn)["id"])

    def get(self, urn: str, semver: str) -> Optional[Dict[str, Any]]:
        return self.versions.one(model_id=self.catalogue.require(urn)["id"], semver=semver)

    def by_id(self, version_id: str) -> Optional[Dict[str, Any]]:
        return self.versions.one(id=version_id)

    def require(self, urn: str, semver: str) -> Dict[str, Any]:
        v = self.get(urn, semver)
        if not v:
            raise RegistryError(f"no version {semver} for {urn}")
        return v

    def approve(self, urn: str, semver: str, actor: str = "system") -> Dict[str, Any]:
        v = self.require(urn, semver)
        if self.policy is not None:
            model = self.catalogue.require(urn)
            # Every fact the gate advertises, not the four this service can
            # see. `blocking_findings` was defaulted to 0 for the life of the
            # gate, so the built-in rule's "not approved over an open blocking
            # finding" had never been able to fire.
            self.policy.check("version:approve", {
                "tier": model.get("tier"), "status": v["status"],
                "has_artifact_digest": bool(v.get("artifact_digest")),
                "has_contract": bool(v.get("contract")),
                **(self.facts.version_approve(model, v) if self.facts else {})},
                f"{urn}@{semver}")
        self.versions.set({"status": "approved"}, id=v["id"])
        self.evidence.append("version_approved", "version", v["id"],
                             {"semver": semver}, actor=actor)
        return {**v, "status": "approved"}
