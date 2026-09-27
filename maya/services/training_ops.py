"""
Training that MAYA directs but does not do, and a re-fit it does only to check one.

**Dispatch.** A training warrant is turned into a job for the firm's own compute. MAYA never
runs it: it returns a *manifest* -- the warrant, the data's download path, the seed, the
target, the split -- signed with the platform key, a short-lived API key scoped to the
warrant's namespace, and two ready-to-submit job definitions, a Kubernetes ``Job`` and a
SageMaker ``CreateTrainingJob`` request. Inside the job, ``maya.sdk.trainer`` downloads the
warrant's data, calls the firm's fit function and uploads the parameters with the data's
checksum and the dispatch id, so the parameter set says which dispatched run produced it.

**Reference re-fit.** For a model MAYA can read, it fits the parameters itself on the
warrant's training rows -- deterministic Levenberg–Marquardt least squares, starting from the
developer's values -- and compares: the two training errors and how far apart the parameters
are. It is a second route to the same answer, recorded as evidence on the warrant, and it
never becomes a parameter set: MAYA checks a fit, it does not supply one. It reads only the
training split, so it is not a holdout attempt.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from maya.core import djson
from maya.core.errors import ValidationFailed
from maya.formula import ir as irmod
from maya.formula.evaluate import evaluate
from maya.security.authz import Principal

MAX_ITERATIONS = 200


def least_squares(
    residual: Any, start: np.ndarray, lo: np.ndarray, hi: np.ndarray
) -> tuple[np.ndarray, int]:
    """Levenberg–Marquardt with a forward-difference Jacobian and box bounds by clipping."""
    x = np.clip(start.astype(float), lo, hi)
    r = residual(x)
    cost, damping = float(r @ r), 1e-3
    for it in range(1, MAX_ITERATIONS + 1):
        step = 1e-6 * np.maximum(np.abs(x), 1.0)
        jac = np.column_stack(
            [(residual(x + step[i] * np.eye(len(x))[i]) - r) / step[i] for i in range(len(x))]
        )
        gram = jac.T @ jac
        try:
            delta = np.linalg.solve(gram + damping * np.diag(np.diag(gram) + 1e-12), -jac.T @ r)
        except np.linalg.LinAlgError:
            break
        trial = np.clip(x + delta, lo, hi)
        tr = residual(trial)
        if float(tr @ tr) < cost:
            converged = cost - float(tr @ tr) < 1e-14 * max(cost, 1e-300)
            x, r, cost, damping = trial, tr, float(tr @ tr), damping / 10
            if converged or np.max(np.abs(delta)) < 1e-12:
                return x, it
        else:
            damping *= 10
            if damping > 1e12:
                break
    return x, it


class TrainingOps:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- dispatch ----------------------------------------------------------------------
    def dispatch(
        self,
        p: Principal,
        warrant_id: str,
        *,
        image: str,
        entrypoint: str = "python train.py",
        maya_url: str = "http://maya:8600",
    ) -> dict[str, Any]:
        """A job definition for the firm's compute, and the key it runs with; nothing runs."""
        if not image.strip():
            raise ValidationFailed("Name the container image the job runs in")
        with self.p.uow() as uow:
            w, ns = self.p.warrants._load(uow, warrant_id)
            self.p.access.require(uow, p, "read", "training_warrant", w)
            if w.get("sealed_at"):
                raise ValidationFailed("The warrant is sealed; its parameters are fixed")
        import uuid

        dispatch_id = str(uuid.uuid4())
        manifest = {
            "dispatch_id": dispatch_id,
            "warrant_id": warrant_id,
            "warrant": self.p.warrants.uri(w, ns),
            "model": w["model_version_id"],
            "featureset": w["featureset_ref"],
            "target": w["spec"].get("target"),
            "seed": w["spec"].get("seed"),
            "split": w["spec"].get("split"),
            "data": f"/api/v1/warrants/training/{warrant_id}/data",
            "parameters": f"/api/v1/warrants/training/{warrant_id}/parameters",
            "issued_to": p.username,
        }
        body = djson.dumps(manifest)
        signer = self.p.signer_or_none()
        signature = signer.sign(body.encode()) if signer else None
        key = self.p.auth.create_api_key(
            p, name=f"training-{dispatch_id[:8]}", namespaces=[ns["name"]], days=1
        )
        env = {
            "MAYA_URL": maya_url,
            "MAYA_WARRANT_ID": warrant_id,
            "MAYA_DISPATCH_ID": dispatch_id,
            "MAYA_MANIFEST": body,
        }
        name = f"maya-train-{dispatch_id[:8]}"
        kubernetes = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {"name": name, "labels": {"maya/warrant": warrant_id[:63]}},
            "spec": {
                "backoffLimit": 0,
                "template": {
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "train",
                                "image": image,
                                "command": ["/bin/sh", "-c", entrypoint],
                                "env": [{"name": k, "value": v} for k, v in env.items()]
                                + [
                                    {
                                        "name": "MAYA_API_KEY",
                                        "valueFrom": {
                                            "secretKeyRef": {"name": name, "key": "api-key"}
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                },
            },
        }
        sagemaker = {
            "TrainingJobName": name,
            "AlgorithmSpecification": {
                "TrainingImage": image,
                "TrainingInputMode": "File",
                "ContainerEntrypoint": ["/bin/sh", "-c", entrypoint],
            },
            "Environment": {**env, "MAYA_API_KEY": "<from your secret store>"},
            "ResourceConfig": {
                "InstanceType": "ml.m5.large",
                "InstanceCount": 1,
                "VolumeSizeInGB": 10,
            },
            "StoppingCondition": {"MaxRuntimeInSeconds": 86400},
            "RoleArn": "<your SageMaker execution role>",
            "OutputDataConfig": {"S3OutputPath": "<unused: parameters go back to MAYA>"},
        }
        with self.p.uow(p.username) as uow:
            uow.audit(
                "warrant.training_dispatched",
                object_type="training_warrant",
                object_ref=manifest["warrant"],
                detail={"dispatch_id": dispatch_id, "image": image, "key_id": key.get("key_id")},
            )
        return {
            "dispatch_id": dispatch_id,
            "manifest": manifest,
            "signature": signature,
            "api_key": key["api_key"],
            "api_key_expires_at": key.get("expires_at"),
            "kubernetes_secret": {"name": name, "key": "api-key"},
            "kubernetes_job": kubernetes,
            "sagemaker_request": sagemaker,
            "note": "MAYA runs nothing: submit one of these to your own compute. The key is shown "
            "once and expires in a day.",
        }

    # -- reference re-fit ----------------------------------------------------------------
    def refit(
        self, p: Principal, warrant_id: str, *, parameter_set_id: str | None = None
    ) -> dict[str, Any]:
        """MAYA's own least-squares fit on the training split, compared with a parameter set."""
        with self.p.uow() as uow:
            w, _ = self.p.warrants._load(uow, warrant_id)
            self.p.access.require(uow, p, "read", "training_warrant", w)
            mv = uow.repo("model_versions").require(w["model_version_id"])
            theirs = (
                uow.repo("parameter_sets").require(parameter_set_id)["values"]
                if parameter_set_id
                else None
            )
        ir = mv["formula_ir"] or {}
        params = irmod.parameter_inputs(ir)
        if irmod.is_opaque(ir) or "body" not in ir or not params:
            raise ValidationFailed(
                "A reference re-fit needs a closed-form model with parameters to fit"
            )
        target = w["spec"].get("target")
        if not target:
            raise ValidationFailed("The warrant declares no target to fit to")
        frame, _ = self.p.warrants.training_frame(w, include_test=False)
        train = frame[frame["_split"] == "train"] if "_split" in frame.columns else frame
        bindings = w["spec"].get("bindings", {})
        inputs = {
            c["name"]: train[bindings.get(c["name"], c["name"])].astype(float).to_numpy()
            for c in irmod.input_contract(ir)
        }
        y = train[target].astype(float).to_numpy()
        keep = np.isfinite(y) & np.all([np.isfinite(v) for v in inputs.values()], axis=0)
        inputs, y = {k: v[keep] for k, v in inputs.items()}, y[keep]
        names = [q["name"] for q in params]
        lo = np.array([(q.get("bounds") or [-np.inf, np.inf])[0] for q in params], dtype=float)
        hi = np.array([(q.get("bounds") or [-np.inf, np.inf])[1] for q in params], dtype=float)

        def predict(x: np.ndarray) -> np.ndarray:
            out = evaluate(ir, inputs, dict(zip(names, (float(v) for v in x))))
            return np.asarray(next(iter(out.values())), dtype=float)

        def residual(x: np.ndarray) -> np.ndarray:
            r = predict(x) - y
            return np.where(np.isfinite(r), r, 1e6)

        start = np.array([float((theirs or {}).get(n, 1.0)) for n in names])
        fitted, iterations = least_squares(residual, start, lo, hi)
        ours = dict(zip(names, (float(v) for v in fitted)))
        rmse_ours = float(np.sqrt(np.mean(residual(fitted) ** 2)))
        result: dict[str, Any] = {
            "rows": int(len(y)),
            "method": "Levenberg-Marquardt least squares, forward-difference Jacobian",
            "iterations": iterations,
            "maya": ours,
            "rmse_maya": rmse_ours,
        }
        if theirs is not None:
            given = np.array([float(theirs.get(n, np.nan)) for n in names])
            rmse_theirs = float(np.sqrt(np.mean(residual(given) ** 2)))
            gap = {
                n: abs(ours[n] - float(theirs[n])) / max(abs(float(theirs[n])), 1e-12)
                for n in names
                if n in theirs
            }
            result.update(
                given=theirs,
                rmse_given=rmse_theirs,
                relative_gap=gap,
                agrees=bool(
                    max(gap.values(), default=0.0) < 1e-3 or rmse_theirs <= rmse_ours * (1 + 1e-6)
                ),
            )
        with self.p.uow(p.username) as uow:
            row = uow.repo("warrant_evidence").add(
                {
                    "training_warrant_id": warrant_id,
                    "parameter_set_id": parameter_set_id,
                    "kind": "reference_refit",
                    "spec": {"method": result["method"]},
                    "result": json.loads(djson.dumps(result)),
                }
            )
            uow.audit(
                "warrant.reference_refit",
                object_type="training_warrant",
                object_ref=warrant_id,
                detail={"agrees": result.get("agrees"), "rmse_maya": rmse_ours},
            )
            return row
